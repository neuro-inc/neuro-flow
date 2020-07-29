import asyncio
import tempfile
from neuromation.api import (
    Client,
    Container,
    HTTPPort,
    JobStatus,
    Resources,
    SecretFile,
    Volume,
)
from neuromation.api.url_utils import uri_from_cli
from types import TracebackType
from typing import AsyncIterator, Dict, Iterable, Optional, Set, Type
from typing_extensions import AsyncContextManager
from yarl import URL

from . import ast
from .context import BatchContext
from .parser import ConfigDir, parse_batch
from .storage import BatchStorage, FinishedTask, StartedTask, TaskResult
from .types import LocalPath


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

        # Check that the yaml is parseable
        flow = parse_batch(self._config_dir.workspace, config_file)
        assert isinstance(flow, ast.BatchFlow)

        ctx = await BatchContext.create(flow)
        for volume in ctx.volumes.values():
            if volume.local is not None:
                # TODO: sync volumes if needed
                pass

        config_content = config_file.read_text()

        bake_id = await self._storage.create_bake(
            batch_name, config_file.name, config_content, ctx.cardinality
        )
        await self._storage.create_attempt(bake_id, 1, ctx.cardinality)
        # TODO: run this function in a job
        await self.process(bake_id)

    async def process(self, bake_id: str) -> None:
        config_dir = LocalPath(tempfile.mkdtemp(prefix=bake_id))
        bake_init = await self._storage.fetch_bake(bake_id)
        config_content = await self._storage.fetch_config(
            bake_id, bake_init.config_file.name
        )
        config_file = config_dir / bake_init.config_file.name
        config_file.write_text(config_content)

        flow = parse_batch(None, config_file)
        assert isinstance(flow, ast.BatchFlow)

        ctx = await BatchContext.create(flow)

        attempt = await self._storage.find_last_attempt(bake_id)
        finished, started = await self._storage.fetch_attempt(
            bake_id, attempt, ctx.cardinality
        )
        while True:
            for t1 in started.values():
                if t1.id in finished:
                    continue
                status = await self._client.jobs.status(t1.raw_id)
                if status.status in (JobStatus.FAILED, JobStatus.SUCCEEDED):
                    finished[t1.id] = await self._storage.finish_task(
                        bake_id,
                        attempt,
                        len(started) + len(finished),
                        ctx.cardinality,
                        t1,
                        status,
                    )

            if len(finished) == ctx.cardinality:
                self._storage.finish_attempt(
                    bake_id,
                    attempt,
                    ctx.cardinality,
                    self._accumulate_result(finished.values()),
                )
                return

            async for task_ctx in self._ready_to_start(ctx, started, finished):
                t2 = await self._start_task(
                    bake_id, attempt, len(started) + len(finished), task_ctx
                )
                started[t2.id] = t2

            await asyncio.sleep(3)

    def _accumulate_result(self, finished: Iterable[FinishedTask]) -> TaskResult:
        # TODO: handle cancelled tasks
        for task in finished:
            if task.status == JobStatus.FAILED:
                return TaskResult.FAILED

        return TaskResult.SUCCEEDED

    async def _ready_to_start(
        self,
        ctx: BatchContext,
        started: Dict[str, StartedTask],
        finished: Dict[str, FinishedTask],
    ) -> AsyncIterator[BatchContext]:
        yield ctx

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
