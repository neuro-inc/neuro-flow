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
)
from neuromation.cli.formatters import ftable  # TODO: extract into a separate library
from types import TracebackType
from typing import (
    AbstractSet,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    Type,
)
from typing_extensions import AsyncContextManager

from . import ast
from .commands import CmdProcessor
from .context import BatchActionContext, BatchContext, DepCtx, NeedsCtx, TaskContext
from .parser import ConfigDir, parse_batch
from .storage import Attempt, BatchStorage, FinishedTask, SkippedTask, StartedTask
from .types import FullID, LocalPath
from .utils import TERMINATED_JOB_STATUSES, format_job_status


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

            top_ctx = await BatchContext.create(
                flow, self._config_dir.workspace, config_file
            )

            click.echo("Find last attempt")
            attempt = await self._storage.find_attempt(bake)
            click.echo(f"Fetch attempt #{attempt.number}")
            started, finished, skipped = await self._storage.fetch_attempt(attempt)

            topos: Dict[
                FullID, Tuple[TaskContext, "graphlib.TopologicalSorter[FullID]"]
            ] = {}
            async for prefix, ctx, topo in self._build_topo(
                (), top_ctx, started, finished, skipped
            ):
                topos[prefix] = (ctx, topo)

            top_topo = topos[()][1]

            while top_topo.is_active():
                for prefix, (ctx, topo) in topos.copy().items():
                    async for action_pre, action_ctx in self._process_topo(
                        attempt, prefix, topo, ctx, started, finished, skipped
                    ):
                        async for new_prefix, new_ctx, new_topo in self._build_topo(
                            action_pre, action_ctx, started, finished, skipped
                        ):
                            topos[new_prefix] = (ctx, topo)

                await self._process_started(attempt, topos, started, finished, skipped)

                # AS: I have no idea what timeout is better;
                # too short value bombards servers,
                # too long timeout makes the waiting longer than expected
                # The missing events subsystem would be great for this task :)
                await asyncio.sleep(1)

            click.echo(f"Attempt #{attempt.number} finished")
            await self._storage.finish_attempt(
                attempt,
                self._accumulate_result(finished.values()),
            )

    def _next_task_no(
        self,
        started: Dict[FullID, StartedTask],
        finished: Dict[FullID, FinishedTask],
        skipped: Dict[FullID, SkippedTask],
    ) -> int:
        return len(started) + len(finished) + len(skipped)

    async def _process_topo(
        self,
        attempt: Attempt,
        prefix: FullID,
        topo: graphlib.TopologicalSorter[FullID],
        ctx: TaskContext,
        started: Dict[FullID, StartedTask],
        finished: Dict[FullID, FinishedTask],
        skipped: Dict[FullID, SkippedTask],
    ) -> AsyncIterator[Tuple[FullID, TaskContext]]:
        for full_id in topo.get_ready():
            if full_id in started:
                continue
            tid = full_id[-1]
            needs = self._build_needs(prefix, ctx.graph[full_id], finished, skipped)
            assert full_id[:-1] == prefix
            if not await ctx.is_enabled(tid, needs=needs):
                # Make task started and immediatelly skipped
                skipped_task = await self._skip_task(
                    attempt, self._next_task_no(started, finished, skipped), full_id
                )
                click.echo(f"Task {skipped_task.id} skipped")
                skipped[skipped_task.id] = skipped_task
                topo.done(full_id)
                continue

            if await ctx.is_action(tid):
                action_ctx = await ctx.with_action(tid, needs=needs)
                st = await self._storage.start_batch_action(
                    attempt, self._next_task_no(started, finished, skipped), full_id
                )
                click.echo(f"Task {st.id} [{st.raw_id}] started")
                started[st.id] = st
                yield full_id, action_ctx
            else:
                task_ctx = await ctx.with_task(tid, needs=needs)
                if task_ctx.task.enable:
                    st = await self._start_task(
                        attempt,
                        self._next_task_no(started, finished, skipped),
                        task_ctx,
                    )
                    click.echo(f"Task {st.id} [{st.raw_id}] started")
                    started[st.id] = st

    async def _process_started(
        self,
        attempt: Attempt,
        topos: Dict[FullID, Tuple[TaskContext, "graphlib.TopologicalSorter[FullID]"]],
        started: Dict[FullID, StartedTask],
        finished: Dict[FullID, FinishedTask],
        skipped: Dict[FullID, SkippedTask],
    ) -> None:
        for st in started.values():
            if st.id in finished:
                continue
            if st.id in skipped:
                continue
            if st.raw_id:
                ctx, topo = topos[st.id[:-1]]
                # (sub)task
                status = await self._client.jobs.status(st.raw_id)
                if status.status in TERMINATED_JOB_STATUSES:
                    finished[st.id] = await self._finish_task(
                        attempt,
                        self._next_task_no(started, finished, skipped),
                        st,
                        status,
                    )
                    click.echo(f"Task {st.id} [{st.raw_id}] has finished")
                    topo.done(st.id)
            else:
                # (sub)action
                ctx, topo = topos[st.id]
                if topo.is_active():
                    # the action is still in progress
                    continue

                # done, make it finished
                assert isinstance(ctx, BatchActionContext)

                needs = self._build_needs(
                    ctx.prefix, ctx.graph.keys(), finished, skipped
                )
                outputs = await ctx.calc_outputs(needs)

                finished[st.id] = await self._storage.finish_batch_action(
                    attempt,
                    self._next_task_no(started, finished, skipped),
                    st,
                    outputs,
                )
                click.echo(f"Action {st.id} has finished")
                topo.done(st.id)

    def _build_needs(
        self,
        prefix: FullID,
        deps: AbstractSet[FullID],
        finished: Mapping[FullID, FinishedTask],
        skipped: Mapping[FullID, SkippedTask],
    ) -> NeedsCtx:
        needs = {}
        for full_id in deps:
            dep_id = full_id[-1]
            if full_id in skipped:
                needs[dep_id] = DepCtx(JobStatus.CANCELLED, {})
            else:
                dep = finished.get(full_id)
                assert dep is not None
                needs[dep_id] = DepCtx(dep.status, dep.outputs)
        return needs

    async def _build_topo(
        self,
        prefix: FullID,
        ctx: TaskContext,
        started: Mapping[FullID, StartedTask],
        finished: Mapping[FullID, FinishedTask],
        skipped: Mapping[FullID, SkippedTask],
    ) -> AsyncIterator[
        Tuple[FullID, TaskContext, "graphlib.TopologicalSorter[FullID]"]
    ]:
        graph = ctx.graph
        topo = graphlib.TopologicalSorter(graph)
        topo.prepare()
        for full_id in graph:
            if full_id in skipped:
                topo.done(full_id)
            if full_id in finished:
                topo.done(full_id)
            elif await ctx.is_action(full_id[-1]):
                if full_id in started:
                    continue
                needs = self._build_needs(prefix, graph[full_id], finished, skipped)
                action_ctx = await ctx.with_action(full_id[-1], needs=needs)
                async for sub_pre, sub_ctx, sub_topo in self._build_topo(
                    full_id, action_ctx, started, finished, skipped
                ):
                    yield sub_pre, sub_ctx, sub_topo
        yield prefix, ctx, topo

    def _accumulate_result(self, finished: Iterable[FinishedTask]) -> JobStatus:
        for task in finished:
            if task.status == JobStatus.CANCELLED:
                return JobStatus.CANCELLED
            elif task.status == JobStatus.FAILED:
                return JobStatus.FAILED

        return JobStatus.SUCCEEDED

    async def _start_task(
        self, attempt: Attempt, task_no: int, task_ctx: TaskContext
    ) -> StartedTask:
        task = task_ctx.task

        preset_name = task.preset
        if preset_name is None:
            preset_name = next(iter(self._client.config.presets))
        preset = self._client.config.presets[preset_name]

        env_dict, secret_env_dict = self._client.parse.env(
            [f"{k}={v}" for k, v in task_ctx.env.items()]
        )
        resources = Resources(
            memory_mb=preset.memory_mb,
            cpu=preset.cpu,
            gpu=preset.gpu,
            gpu_model=preset.gpu_model,
            shm=True,
            tpu_type=preset.tpu_type,
            tpu_software_version=preset.tpu_software_version,
        )
        volumes, secret_files = self._client.parse.volumes(task.volumes)

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
            tags=list(task_ctx.tags),
            description=task.title,
            life_span=task.life_span,
        )
        return await self._storage.start_task(attempt, task_no, task.full_id, job)

    async def _skip_task(
        self, attempt: Attempt, task_no: int, full_id: FullID
    ) -> SkippedTask:
        return await self._storage.skip_task(attempt, task_no, full_id)

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

        started, finished, skipped = await self._storage.fetch_attempt(attempt)
        for task_id in started:
            if task_id in finished:
                rows.append(
                    [".".join(task_id), format_job_status(finished[task_id].status)]
                )
            elif task_id in skipped:
                rows.append([".".join(task_id), format_job_status(JobStatus.CANCELLED)])
            elif task_id in started:
                info = await self._client.jobs.status(started[task_id].raw_id)
                rows.append([".".join(task_id), format_job_status(info.status.value)])
            else:
                # Unreachable currently
                rows.append([".".join(task_id), format_job_status(JobStatus.UNKNOWN)])

        for line in ftable.table(rows):
            click.echo(line)

    async def logs(
        self, bake_id: str, task_id: str, *, attempt_no: int = -1, raw: bool = False
    ) -> None:
        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        attempt = await self._storage.find_attempt(bake, attempt_no)
        started, finished, skipped = await self._storage.fetch_attempt(attempt)
        full_id = tuple(task_id.split("."))
        if full_id in skipped:
            raise click.BadArgumentUsage(f"Task {task_id} was skipped")
        if full_id not in finished:
            if full_id not in started:
                raise click.BadArgumentUsage(f"Unknown task {task_id}")
            else:
                raise click.BadArgumentUsage(f"Task {task_id} is not finished")
        else:
            task = finished[full_id]

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
