import asyncio
import click
import datetime
import sys
import tempfile
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
from neuromation.cli.formatters import ftable  # TODO: extract into a separate library
from types import TracebackType
from typing import Dict, Iterable, List, Optional, Set, Type
from typing_extensions import AsyncContextManager
from yarl import URL

from . import ast
from .commands import CmdProcessor
from .context import BatchContext, DepCtx
from .parser import ConfigDir, parse_batch
from .storage import Attempt, BatchStorage, FinishedTask, StartedTask
from .types import LocalPath
from .utils import format_job_status


if sys.version_info >= (3, 9):
    import graphlib
else:
    from . import backport_graphlib as graphlib


class BatchRunner(AsyncContextManager["BatchRunner"]):
    def __init__(
        self, config_dir: ConfigDir, client: Client, storage: BatchStorage
    ) -> None:
        self._config_dir = config_dir
        self._client = client
        self._storage = storage

    @property
    def project(self) -> str:
        return self._config_dir.workspace.name

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

        click.echo(f"Use config file {config_file}")

        click.echo("Check config")
        # Check that the yaml is parseable
        flow = parse_batch(self._config_dir.workspace, config_file)
        assert isinstance(flow, ast.BatchFlow)

        ctx = await BatchContext.create(flow, self._config_dir.workspace, config_file)
        for volume in ctx.volumes.values():
            if volume.local is not None:
                # TODO: sync volumes if needed
                raise NotImplementedError("Volumes sync is not supported")

        toposorter = graphlib.TopologicalSorter(ctx.graph)
        # check fast for the graph cycle error
        toposorter.prepare()

        click.echo("Config is correct")

        config_content = config_file.read_text()

        click.echo("Create bake")
        bake = await self._storage.create_bake(
            self.project,
            batch_name,
            config_file.name,
            config_content,
            ctx.cardinality,
            ctx.graph,
        )
        click.echo(f"Bake {bake} created")
        # TODO: run this function in a job
        await self.process(bake.project, bake.batch, bake.when, bake.suffix)

    async def process(
        self, project: str, batch: str, when: datetime.datetime, suffix: str
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="bake") as tmp:
            root_dir = LocalPath(tmp)
            click.echo(f"Root dir {root_dir}")
            workspace = root_dir / project
            workspace.mkdir()
            config_dir = workspace / ".neuro"
            config_dir.mkdir()

            click.echo("Fetch bake init")
            bake = await self._storage.fetch_bake(project, batch, when, suffix)
            ("Process %s", bake)
            click.echo("Fetch baked config")
            config_content = await self._storage.fetch_config(bake)
            config_file = config_dir / bake.config_name
            config_file.write_text(config_content)

            click.echo("Parse baked config")
            flow = parse_batch(workspace, config_file)
            assert isinstance(flow, ast.BatchFlow)

            ctx = await BatchContext.create(
                flow, self._config_dir.workspace, config_file
            )

            click.echo("Find last attempt")
            attempt = await self._storage.find_attempt(bake)
            click.echo(f"Fetch attempt #{attempt.number}")
            started, finished = await self._storage.fetch_attempt(attempt)

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
                        needs[dep_id] = DepCtx(dep.status, dep.outputs)
                    task_ctx = await ctx.with_task(tid, needs=needs)
                    st = await self._start_task(
                        attempt, len(started) + len(finished), task_ctx
                    )
                    click.echo(f"Task {st.id} [{st.raw_id}] started")
                    started[st.id] = st

                for st in started.values():
                    if st.id in finished:
                        continue
                    status = await self._client.jobs.status(st.raw_id)
                    if status.status in (JobStatus.FAILED, JobStatus.SUCCEEDED):
                        finished[st.id] = await self._finish_task(
                            attempt,
                            len(started) + len(finished),
                            st,
                            status,
                        )
                        click.echo(f"Task {st.id} [{st.raw_id}] finished")
                        toposorter.done(st.id)

                if len(finished) == ctx.cardinality // 2:
                    click.echo(f"Attempt #{attempt.number} finished")
                    await self._storage.finish_attempt(
                        attempt,
                        self._accumulate_result(finished.values()),
                    )
                    return

                # AS: I have no idea what timeout is better;
                # too short value bombards servers,
                # too long timeout makes the waiting longer than expected
                # The missing events subsystem would be great for this task :)
                await asyncio.sleep(1)

    def _accumulate_result(self, finished: Iterable[FinishedTask]) -> JobStatus:
        # TODO: handle cancelled tasks
        for task in finished:
            if task.status == JobStatus.FAILED:
                return JobStatus.FAILED

        return JobStatus.SUCCEEDED

    async def _start_task(
        self, attempt: Attempt, task_no: int, task_ctx: BatchContext
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
        return await self._storage.start_task(attempt, task_no, task.real_id, job)

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
        attempt: Attempt,
        task_no: int,
        task: StartedTask,
        descr: JobDescription,
    ) -> FinishedTask:
        async with CmdProcessor() as proc:
            async for chunk in self._client.jobs.monitor(task.raw_id):
                async for line in proc.feed_chunk(chunk):
                    pass
            async for line in proc.feed_eof():
                pass
        return await self._storage.finish_task(
            attempt, task_no, task, descr, proc.outputs
        )

    async def list_bakes(self) -> None:
        rows: List[List[str]] = []
        rows.append([click.style("ID", bold=True), click.style("Status", bold=True)])
        async for bake in self._storage.list_bakes(self.project):
            attempt = await self._storage.find_attempt(bake)
            rows.append([bake.bake_id, format_job_status(attempt.result)])

        for line in ftable.table(rows):
            click.echo(line)

    async def inspect(self, bake_id: str, *, attempt_no: int = -1) -> None:
        rows: List[List[str]] = []
        rows.append([click.style("ID", bold=True), click.style("Status", bold=True)])

        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        attempt = await self._storage.find_attempt(bake, attempt_no)

        click.echo(
            " ".join(
                [
                    click.style(f"Attempt #{attempt.number}", bold=True),
                    format_job_status(attempt.result),
                ]
            )
        )

        started, finished = await self._storage.fetch_attempt(attempt)
        for task_id in bake.graph:
            if task_id in finished:
                rows.append([task_id, format_job_status(finished[task_id].status)])
            elif task_id in started:
                info = await self._client.jobs.status(started[task_id].raw_id)
                rows.append([task_id, format_job_status(info.status.value)])
            else:
                rows.append([task_id, format_job_status(JobStatus.UNKNOWN)])

        for line in ftable.table(rows):
            click.echo(line)

    async def logs(
        self, bake_id: str, task_id: str, *, attempt_no: int = -1, raw: bool = False
    ) -> None:
        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        attempt = await self._storage.find_attempt(bake, attempt_no)
        started, finished = await self._storage.fetch_attempt(attempt)
        if task_id not in finished:
            if task_id not in started:
                raise click.BadArgumentUsage(f"Unknown task {task_id}")
            else:
                raise click.BadArgumentUsage(f"Task {task_id} is not finished")
        else:
            task = finished[task_id]

        click.echo(
            " ".join(
                [
                    click.style(f"Attempt #{attempt.number}", bold=True),
                    format_job_status(attempt.result),
                ]
            )
        )
        click.echo(
            " ".join(
                [
                    click.style(f"Task {task_id}", bold=True),
                    format_job_status(task.status),
                ]
            )
        )

        if raw:
            async for chunk in self._client.jobs.monitor(task.raw_id):
                click.echo(chunk.decode("utf-8", "replace"), nl=False)
        else:
            async with CmdProcessor() as proc:
                async for chunk in self._client.jobs.monitor(task.raw_id):
                    async for line in proc.feed_chunk(chunk):
                        click.echo(line.decode("utf-8", "replace"), nl=False)
                async for line in proc.feed_eof():
                    click.echo(line.decode("utf-8", "replace"), nl=False)
