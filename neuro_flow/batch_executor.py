import dataclasses

import asyncio
import base64
import click
import datetime
import json
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
from typing import AbstractSet, AsyncIterator, Dict, List, Tuple

from .commands import CmdProcessor
from .config_loader import BatchRemoteCL
from .context import BatchActionContext, BatchContext, DepCtx, NeedsCtx, TaskContext
from .storage import Attempt, BatchStorage, FinishedTask, SkippedTask, StartedTask
from .types import FullID, LocalPath, TaskStatus
from .utils import TERMINATED_JOB_STATUSES, fmt_id, fmt_raw_id, fmt_status


if sys.version_info >= (3, 9):
    import graphlib
else:
    from . import backport_graphlib as graphlib


class NotFinished(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class ExecutorData:
    project: str
    batch: str
    when: datetime.datetime
    suffix: str

    def serialize(self) -> str:
        data = dataclasses.asdict(self)
        data["when"] = self.when.isoformat()
        return base64.b64encode(json.dumps(data).encode()).decode()

    @classmethod
    def parse(cls, raw: str) -> "ExecutorData":
        raw_json = base64.b64decode(raw).decode()
        data = json.loads(raw_json)
        data["when"] = datetime.datetime.fromisoformat(data["when"])
        return cls(**data)


class BatchExecutor:
    def __init__(
        self,
        executor_data: ExecutorData,
        client: Client,
        storage: BatchStorage,
        polling_timeout: float = 1,
    ) -> None:
        self._executor_data = executor_data
        self._client = client
        self._storage = storage
        self._topos: Dict[
            FullID,
            Tuple[TaskContext, "graphlib.TopologicalSorter[FullID]", List[FullID]],
        ] = {}
        self._started: Dict[FullID, StartedTask] = {}
        self._finished: Dict[FullID, FinishedTask] = {}
        self._skipped: Dict[FullID, SkippedTask] = {}

        # A note about default value:
        # AS: I have no idea what timeout is better;
        # too short value bombards servers,
        # too long timeout makes the waiting longer than expected
        # The missing events subsystem would be great for this task :)
        self._polling_timeout = polling_timeout

    async def run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bake") as tmp:
            root_dir = LocalPath(tmp)
            click.echo(f"Root dir {root_dir}")
            workspace = root_dir / self._executor_data.project
            workspace.mkdir()

            click.echo("Fetch bake init")
            bake = await self._storage.fetch_bake(
                self._executor_data.project,
                self._executor_data.batch,
                self._executor_data.when,
                self._executor_data.suffix,
            )

            click.echo("Fetch configs")
            meta = await self._storage.fetch_configs_meta(bake)
            config_loader = BatchRemoteCL(
                meta,
                load_from_storage=lambda name: self._storage.fetch_config(bake, name),
            )

            top_ctx = await BatchContext.create(config_loader, bake.batch)

            click.echo("Find last attempt")
            attempt = await self._storage.find_attempt(bake)
            if attempt.result in TERMINATED_JOB_STATUSES:
                str_attempt_status = fmt_status(attempt.result)
                click.echo(f"Attempt #{attempt.number} is already {str_attempt_status}")

            click.echo(f"Fetch attempt #{attempt.number}")
            (
                self._started,
                self._finished,
                self._skipped,
            ) = await self._storage.fetch_attempt(attempt)

            async for prefix, ctx, topo in self._build_topo((), top_ctx):
                self._topos[prefix] = (ctx, topo, [])

            top_topo = self._topos[()][1]

            while top_topo.is_active():
                for prefix, (ctx, topo, ready) in self._topos.copy().items():
                    async for action_pre, action_ctx in self._process_topo(
                        attempt,
                        prefix,
                        topo,
                        ready,
                        ctx,
                    ):
                        async for new_prefix, new_ctx, new_topo in self._build_topo(
                            action_pre, action_ctx
                        ):
                            self._topos[new_prefix] = (new_ctx, new_topo, [])

                ok = await self._process_started(attempt)
                if not ok:
                    await self._do_cancellation(attempt)
                    break

                # Check for cancellation
                attempt = await self._storage.find_attempt(bake, attempt.number)
                if attempt.result == JobStatus.CANCELLED:
                    await self._do_cancellation(attempt)
                    click.echo(
                        f"Attempt #{attempt.number} {fmt_status(JobStatus.CANCELLED)}"
                    )
                    return

                await asyncio.sleep(self._polling_timeout)

            attempt_status = self._accumulate_result()
            str_attempt_status = fmt_status(attempt_status)
            await self._storage.finish_attempt(attempt, attempt_status)
            click.echo(f"Attempt #{attempt.number} {str_attempt_status}")

    async def _do_cancellation(self, attempt: Attempt) -> None:
        killed = []
        for st in self._started.values():
            if st.raw_id and st.id not in self._finished:
                await self._client.jobs.kill(st.raw_id)
                killed.append(st.id)
        while any(k_id not in self._finished for k_id in killed):
            await self._process_started(attempt)
            await asyncio.sleep(self._polling_timeout)
        # All jobs stopped, mark as canceled started actions
        for st in self._started.values():
            if st.id not in self._finished:
                assert not st.raw_id
                await self._storage.finish_batch_action(
                    attempt,
                    self._next_task_no(),
                    st,
                    DepCtx(TaskStatus.CANCELLED, {}),
                )

    def _next_task_no(self) -> int:
        return len(self._started) + len(self._finished) + len(self._skipped)

    async def _process_topo(
        self,
        attempt: Attempt,
        prefix: FullID,
        topo: graphlib.TopologicalSorter[FullID],
        ready: List[FullID],
        ctx: TaskContext,
    ) -> AsyncIterator[Tuple[FullID, TaskContext]]:
        running_tasks = {
            k: v
            for k, v in self._started.items()
            if k not in self._finished and k not in self._skipped and v.raw_id
        }
        budget = ctx.strategy.max_parallel - len(running_tasks)
        if budget <= 0:
            return

        ready.extend(topo.get_ready())

        for full_id in ready:
            if full_id in self._started:
                continue
            if full_id in self._finished:
                continue
            if full_id in self._skipped:
                continue
            tid = full_id[-1]
            needs = self._build_needs(prefix, ctx.graph[full_id])
            assert full_id[:-1] == prefix
            if not await ctx.is_enabled(tid, needs=needs):
                # Make task started and immediatelly skipped
                skipped_task = await self._skip_task(
                    attempt, self._next_task_no(), full_id
                )
                str_skipped = click.style("skipped", fg="magenta")
                click.echo(f"Task {fmt_id(full_id)} is {str_skipped}")
                self._skipped[skipped_task.id] = skipped_task
                topo.done(full_id)
                continue

            if await ctx.is_action(tid):
                action_ctx = await ctx.with_action(tid, needs=needs)
                st = await self._storage.start_batch_action(
                    attempt, self._next_task_no(), full_id
                )
                str_started = click.style("started", fg="cyan")
                click.echo(f"Action {fmt_id(st.id)} is {str_started}")
                self._started[st.id] = st
                yield full_id, action_ctx
            else:
                task_ctx = await ctx.with_task(tid, needs=needs)
                ft = await self._storage.check_cache(
                    attempt, self._next_task_no(), full_id, task_ctx
                )
                if ft is not None:
                    str_cached = click.style("cached", fg="magenta")
                    click.echo(
                        f"Task {fmt_id(ft.id)} [{fmt_raw_id(ft.raw_id)}] "
                        f"is {str_cached}"
                    )
                    assert ft.status == JobStatus.SUCCEEDED
                    await self._mark_finished(attempt, ft)
                else:
                    st = await self._start_task(
                        attempt,
                        self._next_task_no(),
                        task_ctx,
                    )
                    str_started = click.style("started", fg="cyan")
                    raw_id = fmt_raw_id(st.raw_id)
                    click.echo(f"Task {fmt_id(st.id)} [{raw_id}] is {str_started}")
                    self._started[st.id] = st
                    budget -= 1
                    if budget <= 0:
                        return

    async def _process_started(self, attempt: Attempt) -> bool:
        for st in self._started.values():
            if st.id in self._finished:
                continue
            if st.id in self._skipped:
                continue
            str_full_id = fmt_id(st.id)
            if st.raw_id:
                ctx, topo, ready = self._topos[st.id[:-1]]
                # (sub)task
                status = await self._client.jobs.status(st.raw_id)
                if status.status in TERMINATED_JOB_STATUSES:
                    if not await self._finish_task(
                        attempt,
                        self._next_task_no(),
                        st,
                        status,
                    ):
                        return False
            else:
                # (sub)action
                ctx, topo, ready = self._topos[st.id]
                if topo.is_active():
                    # the action is still in progress
                    continue

                # done, make it finished
                assert isinstance(ctx, BatchActionContext)

                needs = self._build_needs(ctx.prefix, await ctx.get_output_needs())
                outputs = await ctx.calc_outputs(needs)

                ft = await self._storage.finish_batch_action(
                    attempt,
                    self._next_task_no(),
                    st,
                    outputs,
                )
                self._finished[st.id] = ft
                str_status = fmt_status(self._finished[st.id].status)
                click.echo(
                    f"Action {str_full_id} is {str_status}"
                    + (" with following outputs:" if ft.outputs else "")
                )
                for key, value in ft.outputs.items():
                    click.echo(f"  {key}: {value}")
                parent_ctx, parent_topo, parent_ready = self._topos[st.id[:-1]]
                parent_topo.done(st.id)
                if (
                    self._finished[st.id].status != JobStatus.SUCCEEDED
                    and parent_ctx.strategy.fail_fast
                ):
                    return False
        return True

    def _build_needs(self, prefix: FullID, deps: AbstractSet[FullID]) -> NeedsCtx:
        needs = {}
        for full_id in deps:
            dep_id = full_id[-1]
            if full_id in self._skipped:
                needs[dep_id] = DepCtx(TaskStatus.DISABLED, {})
            else:
                dep = self._finished.get(full_id)
                if dep is None:
                    raise NotFinished(full_id)
                needs[dep_id] = DepCtx(TaskStatus(dep.status), dep.outputs)
        return needs

    async def _build_topo(
        self, prefix: FullID, ctx: TaskContext
    ) -> AsyncIterator[
        Tuple[FullID, TaskContext, "graphlib.TopologicalSorter[FullID]"]
    ]:
        graph = ctx.graph
        topo = graphlib.TopologicalSorter(graph)
        topo.prepare()
        for full_id in graph:
            if full_id in self._skipped:
                topo.done(full_id)
            if full_id in self._finished:
                topo.done(full_id)
            elif await ctx.is_action(full_id[-1]):
                if full_id not in self._started:
                    continue
                needs = self._build_needs(prefix, graph[full_id])
                action_ctx = await ctx.with_action(full_id[-1], needs=needs)
                async for sub_pre, sub_ctx, sub_topo in self._build_topo(
                    full_id, action_ctx
                ):
                    yield sub_pre, sub_ctx, sub_topo
        yield prefix, ctx, topo

    def _accumulate_result(self) -> JobStatus:
        for task in self._finished.values():
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
        volumes_parsed = self._client.parse.volumes(task.volumes)

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
            secret_env=secret_env_dict,
            volumes=list(volumes_parsed.volumes),
            secret_files=list(volumes_parsed.secret_files),
            disk_volumes=list(volumes_parsed.disk_volumes),
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
    ) -> bool:
        async with CmdProcessor() as proc:
            async for chunk in self._client.jobs.monitor(task.raw_id):
                async for line in proc.feed_chunk(chunk):
                    pass
            async for line in proc.feed_eof():
                pass
        ft = await self._storage.finish_task(
            attempt, task_no, task, descr, proc.outputs
        )
        await self._mark_finished(attempt, ft)
        prefix = ft.id[:-1]
        ctx, topo, ready = self._topos[prefix]
        needs = self._build_needs(prefix, ctx.graph[ft.id])
        task_ctx = await ctx.with_task(ft.id[-1], needs=needs)
        await self._storage.write_cache(attempt, task_ctx, ft)
        str_status = fmt_status(ft.status)
        raw_id = fmt_raw_id(ft.raw_id)
        click.echo(
            f"Task {fmt_id(ft.id)} [{raw_id}] is {str_status}"
            + (" with following outputs:" if ft.outputs else "")
        )
        for key, value in ft.outputs.items():
            click.echo(f"  {key}: {value}")
        if descr.status != JobStatus.SUCCEEDED and ctx.strategy.fail_fast:
            return False
        else:
            return True

    async def _mark_finished(self, attempt: Attempt, ft: FinishedTask) -> None:
        self._finished[ft.id] = ft
        ctx, topo, ready = self._topos[ft.id[:-1]]
        topo.done(ft.id)

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
