import dataclasses

import asyncio
import base64
import click
import datetime
import json
import sys
from neuromation.api import Client, Container, HTTPPort, JobStatus, Resources
from typing import (
    AbstractSet,
    Dict,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Set,
    Tuple,
    TypeVar,
)

from .commands import CmdProcessor
from .config_loader import BatchRemoteCL
from .context import (
    BatchActionContext,
    BatchContext,
    DepCtx,
    LocalActionContext,
    NeedsCtx,
    StateCtx,
    TaskContext,
)
from .storage import Attempt, BatchStorage, FinishedTask, StartedTask
from .types import AlwaysT, FullID, TaskStatus
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


_T = TypeVar("_T")


class GraphEmb(Generic[_T]):
    """TopologicalSorter that allows to embed sub graphs in nodes

    Instance of this graph is constructed by provided simple graph
    specification. After that, additional graphs can be embedded
    to nodes of this (or previously embedded) graph. Each node
    has can address using FullID, where each component is names
    node in some graphs. For example, node id ('top', 'node')
    Is a node of graph is embedded to node 'top' of the main top
    level graph.

    Node is considered ready when it is ready inside its graph
    and the parent node is ready. Top level graph is ready by
    default.

    Each graph can be annotated with some metadata.
    """

    def __init__(self, graph: Mapping[str, Iterable[str]], meta: _T):
        topo = graphlib.TopologicalSorter(graph)
        self._topos: Dict[FullID, "graphlib.TopologicalSorter[str]"] = {(): topo}
        self._metas: Dict[FullID, _T] = {(): meta}
        topo.prepare()
        self._ready: Set[FullID] = set()
        self._done: Set[FullID] = set()
        self._embeds_done: Set[FullID] = set()
        self._process_ready(())

    @property
    def is_active(self) -> bool:
        return bool(self._ready)

    def get_ready(self) -> AbstractSet[FullID]:
        return set(self._ready)

    def get_ready_with_meta(self) -> Iterable[Tuple[FullID, _T]]:
        for ready in set(self._ready):
            yield ready, self._metas[ready[:-1]]

    def get_meta(self, node: FullID) -> _T:
        prefix = node[:-1]
        assert prefix in self._topos, f"Parent graph for node {node} not found"
        return self._metas[prefix]

    def get_ready_done_embeds(self) -> AbstractSet[FullID]:
        return self._ready & self._embeds_done

    def mark_done(self, node: FullID) -> None:
        if node in self._topos:
            assert not self._topos[node].is_active(), (
                f"Node '{node}' cannot be set ready when "
                "embeded graph is still in progress"
            )
        prefix, item = node[:-1], node[-1]
        assert prefix in self._topos, f"Parent graph for node {node} not found"
        topo = self._topos[prefix]
        topo.done(item)
        if not topo.is_active() and prefix != ():
            self._embeds_done.add(prefix)
        else:
            self._process_ready(prefix)
        self._ready.remove(node)
        self._done.add(node)

    def embed(self, node: FullID, graph: Mapping[str, Iterable[str]], meta: _T) -> None:
        prefix = node[:-1]
        assert node not in self._done, f"Cannot embed to already done node {node}"
        assert prefix in self._topos, f"Parent graph for node {node} not found"
        self._topos[node] = graphlib.TopologicalSorter(graph)
        self._topos[node].prepare()
        self._metas[node] = meta
        if node in self._ready:
            self._process_ready(node)

    def _process_ready(self, prefix: FullID) -> None:
        # Collects ready node from subgraphs recursively
        for ready in self._topos[prefix].get_ready():
            node = prefix + (ready,)
            self._ready.add(node)
            if node in self._topos:
                self._process_ready(node)


class BakeTasksManager:
    def __init__(self) -> None:
        self._started: Dict[FullID, StartedTask] = {}
        self._finished: Dict[FullID, FinishedTask] = {}

    @property
    def started(self) -> Mapping[FullID, StartedTask]:
        return self._started

    @property
    def finished(self) -> Mapping[FullID, FinishedTask]:
        return self._finished

    @property
    def running_tasks(self) -> Mapping[FullID, StartedTask]:
        return {
            key: value
            for key, value in self.started.items()
            if key not in self.finished and value.raw_id
        }

    def count_running(self, prefix: FullID = ()) -> int:
        def _with_prefix(full_id: FullID) -> bool:
            return all(x == y for x, y in zip(prefix, full_id))

        return len(
            {
                k: v
                for k, v in self._started.items()
                if k not in self._finished and v.raw_id and _with_prefix(k)
            }
        )

    def add_started(self, task: StartedTask) -> None:
        self._started[task.id] = task

    def add_finished(self, task: FinishedTask) -> None:
        self._finished[task.id] = task

    def build_needs(self, prefix: FullID, deps: AbstractSet[str]) -> NeedsCtx:
        needs = {}
        for dep_id in deps:
            full_id = prefix + (dep_id,)
            dep = self._finished.get(full_id)
            if dep is None:
                raise NotFinished(full_id)
            needs[dep_id] = DepCtx(TaskStatus(dep.status), dep.outputs)
        return needs

    def build_state(self, state_from: Optional[FullID]) -> Optional[StateCtx]:
        if state_from is None:
            return None
        dep = self._finished.get(state_from)
        if dep is None:
            raise NotFinished(state_from)
        return dep.state


class BatchExecutor:
    def __init__(
        self,
        top_ctx: TaskContext,
        attempt: Attempt,
        client: Client,
        storage: BatchStorage,
        *,
        polling_timeout: float = 1,
    ) -> None:
        self._top_ctx = top_ctx
        self._attempt = attempt
        self._client = client
        self._storage = storage
        self._graphs: GraphEmb[TaskContext] = GraphEmb(top_ctx.graph, top_ctx)
        self._tasks_mgr = BakeTasksManager()
        self._is_cancelling = False

        # A note about default value:
        # AS: I have no idea what timeout is better;
        # too short value bombards servers,
        # too long timeout makes the waiting longer than expected
        # The missing events subsystem would be great for this task :)
        self._polling_timeout = polling_timeout

    @classmethod
    async def create(
        cls,
        executor_data: ExecutorData,
        client: Client,
        storage: BatchStorage,
        *,
        polling_timeout: float = 1,
    ) -> "BatchExecutor":
        click.echo("Fetch bake data")
        bake = await storage.fetch_bake(
            executor_data.project,
            executor_data.batch,
            executor_data.when,
            executor_data.suffix,
        )

        click.echo("Fetch configs metadata")
        meta = await storage.fetch_configs_meta(bake)
        config_loader = BatchRemoteCL(
            meta,
            load_from_storage=lambda name: storage.fetch_config(bake, name),
        )
        top_ctx = await BatchContext.create(config_loader, bake.batch)

        click.echo("Find last attempt")
        attempt = await storage.find_attempt(bake)

        return cls(
            top_ctx,
            attempt,
            client,
            storage,
            polling_timeout=polling_timeout,
        )

    async def _refresh_attempt(self) -> None:
        self._attempt = await self._storage.find_attempt(
            self._attempt.bake, self._attempt.number
        )

    # Exact task/action contexts helpers

    async def _enter_task_ctx(self, full_id: FullID) -> TaskContext:
        prefix, tid = full_id[:-1], full_id[-1]
        ctx = self._graphs.get_meta(full_id)
        needs = self._tasks_mgr.build_needs(prefix, ctx.graph[tid])
        state = self._tasks_mgr.build_state(await ctx.state_from(tid))
        return await ctx.with_task(tid, needs=needs, state=state)

    async def _enter_local_ctx(self, full_id: FullID) -> LocalActionContext:
        prefix, tid = full_id[:-1], full_id[-1]
        ctx = self._graphs.get_meta(full_id)
        needs = self._tasks_mgr.build_needs(prefix, ctx.graph[tid])
        return await ctx.with_local(tid, needs=needs)

    async def _enter_action_ctx(self, full_id: FullID) -> BatchActionContext:
        prefix, tid = full_id[:-1], full_id[-1]
        ctx = self._graphs.get_meta(full_id)
        needs = self._tasks_mgr.build_needs(prefix, ctx.graph[tid])
        return await ctx.with_action(tid, needs=needs)

    # Graph helpers

    async def _embed_action(self, full_id: FullID) -> None:
        action_ctx = await self._enter_action_ctx(full_id)
        self._graphs.embed(full_id, action_ctx.graph, action_ctx)

    # New tasks processers

    async def _skip_task(self, full_id: FullID) -> None:
        st, ft = await self._storage.skip_task(self._attempt, full_id)
        self._tasks_mgr.add_started(st)
        self._tasks_mgr.add_finished(ft)
        str_skipped = click.style("skipped", fg="magenta")
        click.echo(f"Task {fmt_id(full_id)} is {str_skipped}")
        self._graphs.mark_done(full_id)

    async def _process_local(self, full_id: FullID) -> None:
        raise ValueError("Processing of local actions is not supported")

    async def _process_action(self, full_id: FullID) -> None:
        st = await self._storage.start_action(self._attempt, full_id)
        self._tasks_mgr.add_started(st)
        await self._embed_action(full_id)
        str_started = click.style("started", fg="cyan")
        click.echo(f"Action {fmt_id(st.id)} is {str_started}")

    async def _process_task(self, full_id: FullID) -> None:
        # Check is is task fits in max_parallel
        for n in range(1, len(full_id)):
            node = full_id[:n]
            prefix = node[:-1]
            ctx = self._graphs.get_meta(node)
            if self._tasks_mgr.count_running(prefix) >= ctx.strategy.max_parallel:
                return

        task_ctx = await self._enter_task_ctx(full_id)

        ft = await self._storage.check_cache(self._attempt, full_id, task_ctx)
        if ft is not None:
            str_cached = click.style("cached", fg="magenta")
            click.echo(
                f"Task {fmt_id(ft.id)} [{fmt_raw_id(ft.raw_id)}] " f"is {str_cached}"
            )
            assert ft.status == TaskStatus.SUCCEEDED
            self._tasks_mgr.add_finished(ft)
        else:
            st = await self._start_task(task_ctx)
            self._tasks_mgr.add_started(st)
            str_started = click.style("started", fg="cyan")
            raw_id = fmt_raw_id(st.raw_id)
            click.echo(f"Task {fmt_id(st.id)} [{raw_id}] is {str_started}")

    async def _load_previous_run(self) -> None:
        # Loads tasks that previous executor run processed.
        # Do not handles fail fast option.

        started, finished = await self._storage.fetch_attempt(self._attempt)
        while (started.keys() != self._tasks_mgr.started.keys()) or (
            finished.keys() != self._tasks_mgr.finished.keys()
        ):
            for full_id, ctx in self._graphs.get_ready_with_meta():
                if full_id not in started:
                    continue
                self._tasks_mgr.add_started(started[full_id])
                if await ctx.is_action(full_id[-1]):
                    await self._embed_action(full_id)
                elif full_id in finished:
                    self._tasks_mgr.add_finished(finished[full_id])
                    self._graphs.mark_done(full_id)
            for full_id in self._graphs.get_ready_done_embeds():
                if full_id in finished:
                    self._tasks_mgr.add_finished(finished[full_id])
                    self._graphs.mark_done(full_id)

    async def _should_continue(self) -> bool:
        return self._graphs.is_active

    async def run(self) -> None:
        await self._load_previous_run()

        while await self._should_continue():
            for full_id, ctx in self._graphs.get_ready_with_meta():
                prefix, tid = full_id[:-1], full_id[-1]
                if full_id in self._tasks_mgr.started:
                    continue  # Already started
                needs = self._tasks_mgr.build_needs(prefix, ctx.graph[tid])
                enabled = await ctx.is_enabled(tid, needs=needs)
                if not enabled or (self._is_cancelling and enabled is not AlwaysT()):
                    # Make task started and immediatelly skipped
                    await self._skip_task(full_id)
                    continue
                if await ctx.is_local(tid):
                    await self._process_local(full_id)
                elif await ctx.is_action(tid):
                    await self._process_action(full_id)
                else:
                    await self._process_task(full_id)

            ok = await self._process_started()

            # Check for cancellation
            if not self._is_cancelling:
                await self._refresh_attempt()

                if not ok or self._attempt.result == JobStatus.CANCELLED:
                    self._is_cancelling = True
                    await self._stop_running()

            await asyncio.sleep(self._polling_timeout)

        await self._finish_run()

    async def _finish_run(self) -> None:
        attempt_status = self._accumulate_result()
        str_attempt_status = fmt_status(attempt_status)
        if self._attempt.result not in TERMINATED_JOB_STATUSES:
            await self._storage.finish_attempt(self._attempt, attempt_status)
        click.echo(f"Attempt #{self._attempt.number} {str_attempt_status}")

    async def _stop_running(self) -> None:
        for full_id, st in self._tasks_mgr.running_tasks.items():
            task_context = await self._enter_task_ctx(full_id)
            if task_context.task.enable is not AlwaysT():
                click.echo(f"Task {fmt_id(st.id)} is being killed")
                await self._client.jobs.kill(st.raw_id)

    async def _store_to_cache(self, ft: FinishedTask) -> None:
        task_ctx = await self._enter_task_ctx(ft.id)
        await self._storage.write_cache(self._attempt, task_ctx, ft)

    async def _process_started(self) -> bool:
        # Process tasks
        for full_id, st in self._tasks_mgr.running_tasks.items():
            job_descr = await self._client.jobs.status(st.raw_id)
            if job_descr.status in TERMINATED_JOB_STATUSES:
                async with CmdProcessor() as proc:
                    async for chunk in self._client.jobs.monitor(st.raw_id):
                        async for line in proc.feed_chunk(chunk):
                            pass
                    async for line in proc.feed_eof():
                        pass
                ft = await self._storage.finish_task(
                    self._attempt, st, job_descr, proc.outputs, proc.states
                )
                self._tasks_mgr.add_finished(ft)
                self._graphs.mark_done(full_id)

                await self._store_to_cache(ft)

                str_status = fmt_status(ft.status)
                raw_id = fmt_raw_id(ft.raw_id)
                click.echo(
                    f"Task {fmt_id(ft.id)} [{raw_id}] is {str_status}"
                    + (" with following outputs:" if ft.outputs else "")
                )
                for key, value in ft.outputs.items():
                    click.echo(f"  {key}: {value}")

                task_ctx = await self._enter_task_ctx(st.id)
                if (
                    job_descr.status != JobStatus.SUCCEEDED
                    and task_ctx.strategy.fail_fast
                ):
                    return False
                else:
                    return True
        # Process batch actions
        for full_id in self._graphs.get_ready_done_embeds():
            # done action, make it finished
            ctx = await self._enter_action_ctx(full_id)

            needs = self._tasks_mgr.build_needs(full_id, await ctx.get_output_needs())
            outputs = await ctx.calc_outputs(needs, is_cancelling=self._is_cancelling)

            ft = await self._storage.finish_action(
                self._attempt,
                self._tasks_mgr.started[full_id],
                outputs,
            )
            self._tasks_mgr.add_finished(ft)

            str_status = fmt_status(ft.status)
            click.echo(
                f"Action {fmt_id(ft.id)} is {str_status}"
                + (" with following outputs:" if ft.outputs else "")
            )
            for key, value in ft.outputs.items():
                click.echo(f"  {key}: {value}")

            parent_ctx = self._graphs.get_meta(full_id)
            self._graphs.mark_done(full_id)
            if ft.status != TaskStatus.SUCCEEDED and parent_ctx.strategy.fail_fast:
                return False
        return True

    def _accumulate_result(self) -> JobStatus:
        for task in self._tasks_mgr.finished.values():
            if task.status == TaskStatus.CANCELLED:
                return JobStatus.CANCELLED
            elif task.status == TaskStatus.FAILED:
                return JobStatus.FAILED

        return JobStatus.SUCCEEDED

    async def _start_task(self, task_ctx: TaskContext) -> StartedTask:
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
        return await self._storage.start_task(self._attempt, task.full_id, job)


class LocalsBatchExecutor(BatchExecutor):
    @classmethod
    async def create(
        cls,
        executor_data: ExecutorData,
        client: Client,
        storage: BatchStorage,
        *,
        polling_timeout: Optional[float] = None,
    ) -> "BatchExecutor":
        assert (
            polling_timeout is None
        ), "polling_timeout is disabled for LocalsBatchExecutor"
        return await super(cls, LocalsBatchExecutor).create(
            executor_data, client, storage, polling_timeout=0
        )

    async def _process_local(self, full_id: FullID) -> None:
        local_ctx = await self._enter_local_ctx(full_id)
        st = await self._storage.start_action(self._attempt, full_id)
        self._tasks_mgr.add_started(st)
        str_started = click.style("started", fg="cyan")
        click.echo(f"Local action {fmt_id(st.id)} is {str_started}")

        root_ctx = self._graphs.get_meta(())
        assert isinstance(root_ctx, BatchContext)

        subprocess = await asyncio.create_subprocess_shell(
            local_ctx.shell,
            stdout=asyncio.subprocess.PIPE,
            cwd=root_ctx.flow.workspace,
        )
        (stdout_data, stderr_data) = await subprocess.communicate()
        async with CmdProcessor() as proc:
            async for line in proc.feed_chunk(stdout_data):
                click.echo(line)
            async for line in proc.feed_eof():
                click.echo(line)
        if subprocess.returncode == 0:
            result_status = TaskStatus.SUCCEEDED
        else:
            result_status = TaskStatus.FAILED
        ft = await self._storage.finish_action(
            self._attempt,
            st,
            DepCtx(
                result=result_status,
                outputs=proc.outputs,
            ),
        )
        self._tasks_mgr.add_finished(ft)
        self._graphs.mark_done(full_id)

        str_status = fmt_status(ft.status)
        click.echo(
            f"Action {fmt_id(ft.id)} is {str_status}"
            + (" with following outputs:" if ft.outputs else "")
        )
        for key, value in ft.outputs.items():
            click.echo(f"  {key}: {value}")

    async def _process_action(self, full_id: FullID) -> None:
        pass  # Skip for local

    async def _process_task(self, full_id: FullID) -> None:
        pass  # Skip for local

    async def _should_continue(self) -> bool:
        for full_id, ctx in self._graphs.get_ready_with_meta():
            if await ctx.is_local(full_id[-1]):
                return True
        return False

    async def _finish_run(self) -> None:
        pass  # Do nothing for locals run
