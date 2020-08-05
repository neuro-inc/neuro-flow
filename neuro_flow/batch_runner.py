import asyncio
import sys
import tempfile
from logging import getLogger
from neuromation.api import (
    Client,
    Container,
    HTTPPort,
    JobDescription,
    JobStatus,
    Resources,
    SecretFile,
    Volume,
)
from neuromation.api.url_utils import uri_from_cli
from types import TracebackType
from typing import Dict, Iterable, Optional, Set, Type
from typing_extensions import AsyncContextManager
from yarl import URL

from . import ast
from .commands import CmdProcessor
from .context import BatchContext, DepCtx, Result
from .parser import ConfigDir, parse_batch
from .storage import BatchStorage, FinishedTask, StartedTask
from .types import LocalPath


if sys.version_info >= (3, 9):
    import graphlib
else:
    from . import backport_graphlib as graphlib


log = getLogger(__name__)


class BatchRunner(AsyncContextManager["BatchRunner"]):
    def __init__(
        self, config_dir: ConfigDir, client: Client, storage: BatchStorage
    ) -> None:
        self._config_dir = config_dir
        self._client = client
        self._storage = storage

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "BatchRunner":
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    async def run_subproc(self, exe: str, *args: str) -> None:
        proc = await asyncio.create_subprocess_exec(exe, *args)
        try:
            retcode = await proc.wait()
            if retcode:
                raise SystemExit(retcode)
        finally:
            if proc.returncode is None:
                # Kill neuro process if not finished
                # (e.g. if KeyboardInterrupt or cancellation was received)
                proc.kill()
                await proc.wait()

    async def bake(self, batch_name: str) -> None:
        # batch_name is a name of yaml config inside self._workspace / .neuro
        # folder without the file extension
        config_file = (self._config_dir.config_dir / (batch_name + ".yml")).resolve()

        log.info("Use config file %s", config_file)

        log.info("Check config")
        # Check that the yaml is parseable
        flow = parse_batch(self._config_dir.workspace, config_file)
        assert isinstance(flow, ast.BatchFlow)

        ctx = await BatchContext.create(flow)
        for volume in ctx.volumes.values():
            if volume.local is not None:
                # TODO: sync volumes if needed
                raise NotImplementedError("Volumes sync is not supported")

        toposorter = graphlib.TopologicalSorter(ctx.graph)
        # check fast for the graph cycle error
        toposorter.prepare()

        log.info("Config is correct")

        config_content = config_file.read_text()

        log.info("Create bake")
        bake_id = await self._storage.create_bake(
            batch_name, config_file.name, config_content, ctx.cardinality
        )
        log.info("Bake %s created", bake_id)
        await self._storage.create_attempt(bake_id, 1, ctx.cardinality)
        log.info("Start attempt %d", 1)
        # TODO: run this function in a job
        await self.process(bake_id)

    async def process(self, bake_id: str) -> None:
        log.info("Process %s", bake_id)
        with tempfile.TemporaryDirectory(prefix=bake_id) as tmp:
            root_dir = LocalPath(tmp)
            log.info("Root dir %s", root_dir)
            config_dir = root_dir / ".neuro"
            config_dir.mkdir()
            workspace = config_dir / "workspace"
            workspace.mkdir()

            log.info("Fetch bake init")
            bake_init = await self._storage.fetch_bake(bake_id)
            log.info("Fetch baked config")
            config_content = await self._storage.fetch_config(
                bake_id, bake_init.config_file.name
            )
            config_file = config_dir / bake_init.config_file.name
            config_file.write_text(config_content)

            log.info("Parse baked config")
            flow = parse_batch(workspace, config_file)
            assert isinstance(flow, ast.BatchFlow)

            ctx = await BatchContext.create(flow)

            log.info("Find last attempt")
            attempt = await self._storage.find_last_attempt(bake_id)
            log.info("Fetch attempt %d", attempt)
            finished, started = await self._storage.fetch_attempt(
                bake_id, attempt, ctx.cardinality
            )

            toposorter = graphlib.TopologicalSorter(ctx.graph)
            toposorter.prepare()
            for tid in finished:
                toposorter.done(tid)

            while True:
                for tid in toposorter.get_ready():
                    if tid in started:
                        continue
                    deps = ctx.graph[tid]
                    needs = {}
                    for dep_id in deps:
                        dep = finished.get(dep_id)
                        assert dep is not None
                        needs[dep_id] = DepCtx(dep.result, {})
                    task_ctx = await ctx.with_task(tid, needs=needs)
                    log.info("Task %s started", tid)
                    st = await self._start_task(
                        bake_id, attempt, len(started) + len(finished), task_ctx
                    )
                    started[st.id] = st

                for st in started.values():
                    if st.id in finished:
                        continue
                    status = await self._client.jobs.status(st.raw_id)
                    if status.status in (JobStatus.FAILED, JobStatus.SUCCEEDED):
                        log.info("Task %s finished", tid)
                        finished[st.id] = await self._finish_task(
                            bake_id,
                            attempt,
                            len(started) + len(finished),
                            ctx.cardinality,
                            st,
                            status,
                        )
                        toposorter.done(st.id)

                if len(finished) == ctx.cardinality // 2:
                    log.info("Attempt %d finished", attempt)
                    await self._storage.finish_attempt(
                        bake_id,
                        attempt,
                        ctx.cardinality,
                        self._accumulate_result(finished.values()),
                    )
                    return

                # AS: I have no idea what timeout is better;
                # too short value bombards servers,
                # too long timeout makes the waiting longer than expected
                # The missing events subsystem would be great for this task :)
                await asyncio.sleep(1)

    def _accumulate_result(self, finished: Iterable[FinishedTask]) -> Result:
        # TODO: handle cancelled tasks
        for task in finished:
            if task.status == JobStatus.FAILED:
                return Result.FAILED

        return Result.SUCCEEDED

    async def _start_task(
        self, bake_id: str, attempt: int, task_no: int, task_ctx: BatchContext
    ) -> StartedTask:
        task = task_ctx.task

        preset_name = task.preset
        if preset_name is None:
            preset_name = next(iter(self._client.config.presets))
        preset = self._client.config.presets[preset_name]

        env_dict = dict(task_ctx.env)
        secret_env_dict = self._extract_secret_env(env_dict)
        resources = Resources(
            memory_mb=preset.memory_mb,
            cpu=preset.cpu,
            gpu=preset.gpu,
            gpu_model=preset.gpu_model,
            shm=True,
            tpu_type=preset.tpu_type,
            tpu_software_version=preset.tpu_software_version,
        )
        input_secret_files = {vol for vol in task.volumes if vol.startswith("secret:")}
        input_volumes = set(task.volumes) - input_secret_files
        secret_files = await self._build_secret_files(input_secret_files)
        volumes = await self._build_volumes(input_volumes)

        http_auth = task.http_auth
        if http_auth is None:
            http_auth = HTTPPort.requires_auth

        container = Container(
            image=self._client.parse.remote_image(task.image),
            entrypoint=task.entrypoint,
            command=task.cmd,
            http=HTTPPort(task.http_port, http_auth) if task.http_port else None,
            resources=resources,
            env=env_dict,
            volumes=list(volumes),
            secret_env=secret_env_dict,
            secret_files=list(secret_files),
            tty=False,
        )

        job = await self._client.jobs.run(
            container,
            is_preemptible=preset.is_preemptible,
            name=task.name,
            tags=list(task.tags),
            description=task.title,
            life_span=task.life_span,
        )
        return await self._storage.start_task(
            bake_id, attempt, task_no, task_ctx.cardinality, task.real_id, job
        )

    def _extract_secret_env(self, env_dict: Dict[str, str]) -> Dict[str, URL]:
        secret_env_dict = {}
        for name, val in env_dict.copy().items():
            if val.startswith("secret:"):
                secret_env_dict[name] = uri_from_cli(
                    val,
                    self._client.username,
                    self._client.cluster_name,
                    allowed_schemes=("secret"),
                )
                del env_dict[name]
        return secret_env_dict

    async def _build_volumes(self, input_volumes: Iterable[str]) -> Set[Volume]:
        volumes: Set[Volume] = set()

        for vol in input_volumes:
            volumes.add(self._client.parse.volume(vol))
        return volumes

    async def _build_secret_files(self, input_volumes: Set[str]) -> Set[SecretFile]:
        secret_files: Set[SecretFile] = set()
        for volume in input_volumes:
            parts = volume.split(":")
            if len(parts) != 3:
                raise ValueError(f"Invalid secret file specification '{volume}'")
            container_path = parts.pop()
            secret_uri = uri_from_cli(
                ":".join(parts),
                self._client.username,
                self._client.cluster_name,
                allowed_schemes=("secret"),
            )
            secret_files.add(SecretFile(secret_uri, container_path))
        return secret_files

    async def _finish_task(
        self,
        bake_id: str,
        attempt_no: int,
        task_no: int,
        cardinality: int,
        task: StartedTask,
        descr: JobDescription,
    ) -> FinishedTask:
        async with CmdProcessor() as proc:
            buf = bytearray()
            async for chunk in self._client.jobs.monitor(task.raw_id):
                buf.extend(chunk)
                if b"\n" in buf:
                    blines = buf.splitlines(keepends=True)
                    buf = blines.pop(-1)
                    for bline in blines:
                        line = bline.decode("utf-8", "replace")
                        await proc.feed(line)
            line = buf.decode("utf-8", "replace")
            await proc.feed(line)
        return await self._storage.finish_task(
            bake_id, attempt_no, task_no, cardinality, task, descr
        )
