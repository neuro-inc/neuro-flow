import dataclasses

import asyncio
import base64
import datetime
import json
import os
import sys
from collections import defaultdict
from neuro_sdk import Client, HTTPPort, JobStatus, ResourceNotFound
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskID, TextColumn
from typing import (
    AbstractSet,
    AsyncIterator,
    Dict,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Set,
    Tuple,
    TypeVar,
)

from . import ast
from .colored_topo_sorter import ColoredTopoSorter
from .commands import CmdProcessor
from .config_loader import BatchRemoteCL
from .context import (
    BaseBatchContext,
    DepCtx,
    LocalTask,
    NeedsCtx,
    RunningBatchActionFlow,
    RunningBatchBase,
    RunningBatchFlow,
    StateCtx,
    Task,
    TaskMeta,
)
from .expr import EvalError
from .storage import Attempt, Bake, FinishedTask, StartedTask, Storage, _dt2str
from .types import AlwaysT, FullID, TaskStatus
from .utils import (
    TERMINATED_JOB_STATUSES,
    TERMINATED_TASK_STATUSES,
    fmt_id,
    fmt_raw_id,
    fmt_status,
)


if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


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

    def get_bake_id(self) -> str:
        # Todo: this is duplication with code in storage.py,
        # remove when platform service will be added
        return "_".join([self.batch, _dt2str(self.when), self.suffix])


async def get_running_flow(
    bake: Bake, client: Client, storage: Storage
) -> RunningBatchFlow:
    meta = await storage.fetch_configs_meta(bake)
    config_loader = BatchRemoteCL(
        meta,
        load_from_storage=lambda name: storage.fetch_config(bake, name),
        client=client,
    )
    return await RunningBatchFlow.create(
        config_loader=config_loader,
        batch=bake.batch,
        bake_id=bake.bake_id,
        params=bake.params,
    )


_T = TypeVar("_T")


class Graph(Generic[_T]):
    """TopologicalSorter that allows to embed sub graphs in nodes

    Instance of this graph is constructed by provided simple graph
    specification. After that, additional graphs can be embedded
    to nodes of this (or previously embedded) graph. Each node
    has address of type FullID, where each component is names
    node in some graphs. For example, node id ('top', 'node')
    is a node of graph embedded to node 'top' of the main top
    level graph.

    Node is considered ready when it is ready inside its graph
    and the parent node is ready. Top level graph is ready by
    default.

    Each graph can be annotated with some metadata.
    """

    def __init__(self, graph: Mapping[str, Mapping[str, ast.NeedsLevel]], meta: _T):
        topo = ColoredTopoSorter(graph)
        self._topos: Dict[FullID, ColoredTopoSorter[str, ast.NeedsLevel]] = {(): topo}
        self._sizes: Dict[FullID, int] = {(): len(graph)}
        self._metas: Dict[FullID, _T] = {(): meta}
        self._ready: Set[FullID] = set()
        self._done: Set[FullID] = set()
        self._ready_to_mark_embeds: Dict[ast.NeedsLevel, Set[FullID]] = defaultdict(set)
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

    def get_ready_to_mark_running_embeds(self) -> AbstractSet[FullID]:
        return set(self._ready_to_mark_embeds[ast.NeedsLevel.RUNNING])

    def get_ready_to_mark_done_embeds(self) -> AbstractSet[FullID]:
        return set(self._ready_to_mark_embeds[ast.NeedsLevel.COMPLETED])

    def get_size(self, prefix: FullID) -> int:
        return self._sizes[prefix]

    def _mark_node(self, node: FullID, level: ast.NeedsLevel) -> None:
        if node in self._topos:
            assert node in self._ready_to_mark_embeds[level], (
                f"Node '{node}' cannot be marked to {level} when "
                f"embeded graph is not all marked with {level}"
            )
            self._ready_to_mark_embeds[level].remove(node)
        prefix, item = node[:-1], node[-1]
        assert prefix in self._topos, f"Parent graph for node {node} not found"
        topo = self._topos[prefix]
        topo.mark(item, level)
        if topo.is_all_colored(level) and prefix != ():
            self._ready_to_mark_embeds[level].add(prefix)
        else:
            self._process_ready(prefix)

    def mark_running(self, node: FullID) -> None:
        self._mark_node(node, ast.NeedsLevel.RUNNING)

    def mark_done(self, node: FullID) -> None:
        self._mark_node(node, ast.NeedsLevel.COMPLETED)
        self._ready.remove(node)
        self._done.add(node)

    def embed(
        self, node: FullID, graph: Mapping[str, Mapping[str, ast.NeedsLevel]], meta: _T
    ) -> None:
        prefix = node[:-1]
        assert node not in self._done, f"Cannot embed to already done node {node}"
        assert prefix in self._topos, f"Parent graph for node {node} not found"
        self._topos[node] = ColoredTopoSorter(graph)
        self._sizes[node] = len(graph)
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
        self._running: Dict[FullID, StartedTask] = {}
        self._finished: Dict[FullID, FinishedTask] = {}

    @property
    def started(self) -> Mapping[FullID, StartedTask]:
        return self._started

    @property
    def running(self) -> Mapping[FullID, StartedTask]:
        return self._running

    @property
    def finished(self) -> Mapping[FullID, FinishedTask]:
        return self._finished

    @property
    def unfinished_tasks(self) -> Mapping[FullID, StartedTask]:
        return {
            key: value
            for key, value in self.started.items()
            if key not in self.finished and value.raw_id
        }

    def count_unfinished(self, prefix: FullID = ()) -> int:
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

    def add_running(self, task: StartedTask) -> None:
        self._running[task.id] = task

    def add_finished(self, task: FinishedTask) -> None:
        self._finished[task.id] = task

    def build_needs(self, prefix: FullID, deps: AbstractSet[str]) -> NeedsCtx:
        needs = {}
        for dep_id in deps:
            full_id = prefix + (dep_id,)
            dep = self._finished.get(full_id)
            if dep is None:
                raise NotFinished(full_id)
            status = TaskStatus(dep.status)
            if status == TaskStatus.CACHED:
                status = TaskStatus.SUCCEEDED
            needs[dep_id] = DepCtx(status, dep.outputs)
        return needs

    def build_state(self, prefix: FullID, state_from: Optional[str]) -> StateCtx:
        if state_from is None:
            return {}
        full_id = prefix + (state_from,)
        dep = self._finished.get(full_id)
        if dep is None:
            raise NotFinished(full_id)
        return dep.state


class BatchExecutor:
    def __init__(
        self,
        console: Console,
        flow: RunningBatchFlow,
        attempt: Attempt,
        client: Client,
        storage: Storage,
        *,
        polling_timeout: float = 1,
        transient_progress: bool = False,
    ) -> None:
        self._progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[progress.remaining]{task.elapsed:.0f} sec"),
            console=console,
            auto_refresh=False,
            transient=transient_progress,
        )
        self._top_flow = flow
        self._attempt = attempt
        self._client = client
        self._storage = storage
        self._graphs: Graph[RunningBatchBase[BaseBatchContext]] = Graph(
            flow.graph, flow
        )
        self._tasks_mgr = BakeTasksManager()
        self._is_cancelling = False

        # A note about default value:
        # AS: I have no idea what timeout is better;
        # too short value bombards servers,
        # too long timeout makes the waiting longer than expected
        # The missing events subsystem would be great for this task :)
        self._polling_timeout = polling_timeout
        self._bars: Dict[FullID, TaskID] = {}

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        console: Console,
        executor_data: ExecutorData,
        client: Client,
        storage: Storage,
        *,
        polling_timeout: float = 1,
        transient_progress: bool = False,
    ) -> AsyncIterator["BatchExecutor"]:
        console.log("Fetch bake data")
        bake = await storage.fetch_bake(
            executor_data.project,
            executor_data.batch,
            executor_data.when,
            executor_data.suffix,
        )

        console.log("Fetch configs metadata")
        flow = await get_running_flow(bake, client, storage)

        console.log("Find last attempt")
        attempt = await storage.find_attempt(bake)
        console.log(f"Execute attempt #{attempt.number}")

        ret = cls(
            console,
            flow,
            attempt,
            client,
            storage,
            polling_timeout=polling_timeout,
            transient_progress=transient_progress,
        )
        ret._start()
        try:
            yield ret
        finally:
            ret._stop()

    def _start(self) -> None:
        pass

    def _stop(self) -> None:
        pass

    async def _refresh_attempt(self) -> None:
        self._attempt = await self._storage.find_attempt(
            self._attempt.bake, self._attempt.number
        )

    def _only_completed_needs(
        self, needs: Mapping[str, ast.NeedsLevel]
    ) -> AbstractSet[str]:
        return {
            task_id
            for task_id, level in needs.items()
            if level == ast.NeedsLevel.COMPLETED
        }

    # Exact task/action contexts helpers
    async def _get_meta(self, full_id: FullID) -> TaskMeta:
        prefix, tid = full_id[:-1], full_id[-1]
        flow = self._graphs.get_meta(full_id)
        needs = self._tasks_mgr.build_needs(
            prefix, self._only_completed_needs(flow.graph[tid])
        )
        state = self._tasks_mgr.build_state(prefix, await flow.state_from(tid))
        return await flow.get_meta(tid, needs=needs, state=state)

    async def _get_task(self, full_id: FullID) -> Task:
        prefix, tid = full_id[:-1], full_id[-1]
        flow = self._graphs.get_meta(full_id)
        needs = self._tasks_mgr.build_needs(
            prefix, self._only_completed_needs(flow.graph[tid])
        )
        state = self._tasks_mgr.build_state(prefix, await flow.state_from(tid))
        return await flow.get_task(prefix, tid, needs=needs, state=state)

    async def _get_local(self, full_id: FullID) -> LocalTask:
        prefix, tid = full_id[:-1], full_id[-1]
        flow = self._graphs.get_meta(full_id)
        needs = self._tasks_mgr.build_needs(
            prefix, self._only_completed_needs(flow.graph[tid])
        )
        return await flow.get_local(tid, needs=needs)

    async def _get_action(self, full_id: FullID) -> RunningBatchActionFlow:
        prefix, tid = full_id[:-1], full_id[-1]
        flow = self._graphs.get_meta(full_id)
        needs = self._tasks_mgr.build_needs(
            prefix, self._only_completed_needs(flow.graph[tid])
        )
        return await flow.get_action(tid, needs=needs)

    # Graph helpers

    async def _embed_action(self, full_id: FullID) -> None:
        action = await self._get_action(full_id)
        self._graphs.embed(full_id, action.graph, action)
        task_id = self._progress.add_task(
            ".".join(full_id),
            completed=0,
            total=self._graphs.get_size(full_id) * 3,
        )
        self._bars[full_id] = task_id

    def _mark_started(self, st: StartedTask) -> None:
        self._tasks_mgr.add_started(st)
        task_id = self._bars[st.id[:-1]]
        self._progress.update(task_id, advance=1, refresh=True)

    def _mark_running(self, st: StartedTask) -> None:
        self._tasks_mgr.add_running(st)
        self._graphs.mark_running(st.id)
        task_id = self._bars[st.id[:-1]]
        self._progress.update(task_id, advance=1, refresh=True)

    def _mark_finished(self, ft: FinishedTask, advance: int = 1) -> None:
        self._tasks_mgr.add_finished(ft)
        self._graphs.mark_done(ft.id)
        task_id = self._bars[ft.id[:-1]]
        self._progress.update(task_id, advance=advance, refresh=True)

    # New tasks processers

    async def _skip_task(self, full_id: FullID) -> None:
        st, ft = await self._storage.skip_task(self._attempt, full_id)
        self._mark_started(st)
        self._mark_finished(ft, advance=2)
        self._progress.log("Task", fmt_id(full_id), "is", TaskStatus.SKIPPED)

    async def _process_local(self, full_id: FullID) -> None:
        raise ValueError("Processing of local actions is not supported")

    async def _process_action(self, full_id: FullID) -> None:
        st = await self._storage.start_action(self._attempt, full_id)
        self._mark_started(st)
        await self._embed_action(full_id)
        self._progress.log(f"Action", fmt_id(st.id), "is", TaskStatus.PENDING)

    async def _process_task(self, full_id: FullID) -> None:

        task = await self._get_task(full_id)

        # Check is is task fits in max_parallel
        for n in range(1, len(full_id) + 1):
            node = full_id[:n]
            prefix = node[:-1]
            if self._tasks_mgr.count_unfinished(prefix) >= task.strategy.max_parallel:
                return

        cache_strategy = task.cache.strategy
        if cache_strategy == ast.CacheStrategy.NONE:
            ft = None
        else:
            assert cache_strategy == ast.CacheStrategy.DEFAULT
            ft = await self._storage.check_cache(
                self._attempt,
                full_id,
                task.caching_key,
                datetime.timedelta(task.cache.life_span),
            )

        if ft is not None:
            self._progress.log(
                "Task", fmt_id(ft.id), fmt_raw_id(ft.raw_id), "is", TaskStatus.CACHED
            )
            assert ft.status == TaskStatus.CACHED
            self._mark_finished(ft, advance=3)
        else:
            st = await self._start_task(full_id, task)
            self._mark_started(st)
            self._progress.log(
                "Task", fmt_id(st.id), fmt_raw_id(st.raw_id), "is", TaskStatus.PENDING
            )

    async def _load_previous_run(self) -> None:
        # Loads tasks that previous executor run processed.
        # Do not handles fail fast option.

        root_id = ()
        task_id = self._progress.add_task(
            f"<{self._attempt.bake.batch}>",
            completed=0,
            total=self._graphs.get_size(root_id) * 3,
        )
        self._bars[root_id] = task_id

        started, finished = await self._storage.fetch_attempt(self._attempt)
        # Fetch info about running from server
        running: Dict[FullID, StartedTask] = {
            ft.id: started[ft.id] for ft in finished.values()
        }  # All finished are considered as running
        for st in started.values():
            if not st.raw_id:
                continue
            try:
                job_descr = await self._client.jobs.status(st.raw_id)
            except ResourceNotFound:
                pass
            else:
                if job_descr.status in {JobStatus.RUNNING, JobStatus.SUCCEEDED}:
                    running[st.id] = st
        # Rebuild data in graph and task_mgr
        while (started.keys() != self._tasks_mgr.started.keys()) or (
            finished.keys() != self._tasks_mgr.finished.keys()
        ):
            for full_id, ctx in self._graphs.get_ready_with_meta():
                if full_id in self._tasks_mgr.started or full_id not in started:
                    continue
                self._mark_started(started[full_id])
                if await ctx.is_action(full_id[-1]):
                    await self._embed_action(full_id)
                else:
                    if full_id in running:
                        self._mark_running(running[full_id])
                    if full_id in finished:
                        self._mark_finished(finished[full_id])
            for full_id in self._graphs.get_ready_to_mark_running_embeds():
                self._mark_running(started[full_id])
            for full_id in self._graphs.get_ready_to_mark_done_embeds():
                if full_id in finished:
                    self._mark_finished(finished[full_id])

    async def _should_continue(self) -> bool:
        return self._graphs.is_active

    async def run(self) -> TaskStatus:
        with self._progress:
            try:
                result = await self._run()
            except (KeyboardInterrupt, asyncio.CancelledError):
                await self._cancel_unfinished()
                result = TaskStatus.CANCELLED
            except Exception as exp:
                await self.log_error(exp)
                await self._cancel_unfinished()
                result = TaskStatus.FAILED
        await self._finish_run(result)
        return result

    async def log_error(self, exp: Exception) -> None:
        if isinstance(exp, EvalError):
            self._progress.log(f"[red][b]ERROR:[/b] {exp}[/red]")
        else:
            # Looks like this is some bug in our code, so we should print stacktrace
            # for easier debug
            self._progress.console.print_exception(show_locals=True)
            self._progress.log(
                "[red][b]ERROR:[/b] Some unknown error happened. Please report "
                "an issue to https://github.com/neuro-inc/neuro-flow/issues/new "
                "with traceback printed above.[/red]"
            )

    async def _run(self) -> TaskStatus:
        await self._load_previous_run()

        job_id = os.environ.get("NEURO_JOB_ID")
        if job_id:
            # store job id as executor id
            await self._storage.store_executor_id(self._attempt, job_id)

        if self._attempt.result in TERMINATED_TASK_STATUSES:
            # If attempt is already terminated, just clean up tasks
            # and exit
            await self._cancel_unfinished()
            return self._attempt.result

        while await self._should_continue():
            for full_id, flow in self._graphs.get_ready_with_meta():
                tid = full_id[-1]
                if full_id in self._tasks_mgr.started:
                    continue  # Already started
                meta = await self._get_meta(full_id)
                if not meta.enable or (
                    self._is_cancelling and meta.enable is not AlwaysT()
                ):
                    # Make task started and immediatelly skipped
                    await self._skip_task(full_id)
                    continue
                if await flow.is_local(tid):
                    await self._process_local(full_id)
                elif await flow.is_action(tid):
                    await self._process_action(full_id)
                else:
                    await self._process_task(full_id)

            ok = await self._process_started()

            # Check for cancellation
            if not self._is_cancelling:
                await self._refresh_attempt()

                if not ok or self._attempt.result == TaskStatus.CANCELLED:
                    await self._cancel_unfinished()

            await asyncio.sleep(self._polling_timeout)

        return self._accumulate_result()

    async def _finish_run(self, attempt_status: TaskStatus) -> None:
        if self._attempt.result not in TERMINATED_TASK_STATUSES:
            await self._storage.finish_attempt(self._attempt, attempt_status)
        self._progress.print(
            Panel(
                f"[b]Attempt #{self._attempt.number}[/b] {fmt_status(attempt_status)}"
            ),
            justify="center",
        )

    async def _cancel_unfinished(self) -> None:
        self._is_cancelling = True
        for full_id, st in self._tasks_mgr.unfinished_tasks.items():
            task = await self._get_task(full_id)
            if task.enable is not AlwaysT():
                self._progress.log(f"Task {fmt_id(st.id)} is being killed")
                await self._client.jobs.kill(st.raw_id)

    async def _store_to_cache(self, ft: FinishedTask) -> None:
        task = await self._get_task(ft.id)
        cache_strategy = task.cache.strategy
        if cache_strategy == ast.CacheStrategy.NONE:
            return
        if ft.status != TaskStatus.SUCCEEDED:
            return

        await self._storage.write_cache(self._attempt, ft, task.caching_key)

    async def _process_started(self) -> bool:
        # Process tasks
        for full_id, st in self._tasks_mgr.unfinished_tasks.items():
            job_descr = await self._client.jobs.status(st.raw_id)
            if (
                job_descr.status in {JobStatus.RUNNING, JobStatus.SUCCEEDED}
                and full_id not in self._tasks_mgr.running
            ):
                self._mark_running(st)
                self._progress.log(
                    "Task",
                    fmt_id(st.id),
                    fmt_raw_id(st.raw_id),
                    "is",
                    TaskStatus.RUNNING,
                )
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
                self._mark_finished(ft)

                await self._store_to_cache(ft)

                self._progress.log(
                    "Task",
                    fmt_id(ft.id),
                    fmt_raw_id(ft.raw_id),
                    "is",
                    ft.status,
                    (" with following outputs:" if ft.outputs else ""),
                )
                for key, value in ft.outputs.items():
                    self._progress.log(f"  {key}: {value}")

                task_meta = await self._get_meta(full_id)
                if ft.status != TaskStatus.SUCCEEDED and task_meta.strategy.fail_fast:
                    return False
        # Process batch actions
        for full_id in self._graphs.get_ready_to_mark_running_embeds():
            st = self._tasks_mgr.started[full_id]
            self._mark_running(st)
            self._progress.log(
                "Action",
                fmt_id(st.id),
                fmt_raw_id(st.raw_id),
                "is",
                TaskStatus.RUNNING,
            )

        for full_id in self._graphs.get_ready_to_mark_done_embeds():
            # done action, make it finished
            ctx = await self._get_action(full_id)

            results = self._tasks_mgr.build_needs(full_id, ctx.graph.keys())
            outputs = await ctx.calc_outputs(results)

            ft = await self._storage.finish_action(
                self._attempt,
                self._tasks_mgr.started[full_id],
                outputs,
            )
            self._mark_finished(ft)

            self._progress.log(
                f"Action {fmt_id(ft.id)} is",
                ft.status,
                (" with following outputs:" if ft.outputs else ""),
            )
            for key, value in ft.outputs.items():
                self._progress.log(f"  {key}: {value}")

            task_id = self._bars[full_id]
            self._progress.remove_task(task_id)

            task_meta = await self._get_meta(full_id)
            if ft.status != TaskStatus.SUCCEEDED and task_meta.strategy.fail_fast:
                return False
        return True

    def _accumulate_result(self) -> TaskStatus:
        for task in self._tasks_mgr.finished.values():
            if task.status == TaskStatus.CANCELLED:
                return TaskStatus.CANCELLED
            elif task.status == TaskStatus.FAILED:
                return TaskStatus.FAILED

        return TaskStatus.SUCCEEDED

    async def _start_task(self, full_id: FullID, task: Task) -> StartedTask:

        preset_name = task.preset
        if preset_name is None:
            preset_name = next(iter(self._client.config.presets))

        env_dict, secret_env_dict = self._client.parse.env(
            [f"{k}={v}" for k, v in task.env.items()]
        )

        volumes_parsed = self._client.parse.volumes(task.volumes)
        volumes = list(volumes_parsed.volumes)

        http_auth = task.http_auth
        if http_auth is None:
            http_auth = HTTPPort.requires_auth

        job = await self._client.jobs.start(
            shm=True,
            tty=False,
            image=self._client.parse.remote_image(task.image),
            preset_name=preset_name,
            entrypoint=task.entrypoint,
            command=task.cmd,
            http=HTTPPort(task.http_port, http_auth) if task.http_port else None,
            env=env_dict,
            secret_env=secret_env_dict,
            volumes=volumes,
            working_dir=str(task.workdir) if task.workdir else None,
            secret_files=list(volumes_parsed.secret_files),
            disk_volumes=list(volumes_parsed.disk_volumes),
            name=task.name,
            tags=list(task.tags),
            description=task.title,
            life_span=task.life_span,
            schedule_timeout=task.schedule_timeout,
            pass_config=bool(task.pass_config),
        )
        return await self._storage.start_task(self._attempt, full_id, job)


class LocalsBatchExecutor(BatchExecutor):
    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        console: Console,
        executor_data: ExecutorData,
        client: Client,
        storage: Storage,
        *,
        polling_timeout: Optional[float] = None,
    ) -> AsyncIterator["BatchExecutor"]:
        assert (
            polling_timeout is None
        ), "polling_timeout is disabled for LocalsBatchExecutor"
        async with super(cls, LocalsBatchExecutor).create(
            console,
            executor_data,
            client,
            storage,
            polling_timeout=0,
            transient_progress=True,
        ) as ret:
            yield ret

    async def _process_local(self, full_id: FullID) -> None:
        local = await self._get_local(full_id)
        st = await self._storage.start_action(self._attempt, full_id)
        self._mark_started(st)
        self._progress.log(f"Local action {fmt_id(st.id)} is", TaskStatus.PENDING)
        subprocess = await asyncio.create_subprocess_shell(
            local.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._top_flow.workspace,
        )
        (stdout_data, stderr_data) = await subprocess.communicate()
        async with CmdProcessor() as proc:
            async for line in proc.feed_chunk(stdout_data):
                self._progress.log(line.decode())
            async for line in proc.feed_eof():
                self._progress.log(line.decode())
        if stderr_data:
            self._progress.log(stderr_data.decode())
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
        self._mark_finished(ft)

        self._progress.log(
            f"Action {fmt_id(ft.id)} is",
            ft.status,
            (" with following outputs:" if ft.outputs else ""),
        )
        for key, value in ft.outputs.items():
            self._progress.log(f"  {key}: {value}")

    async def _process_task(self, full_id: FullID) -> None:
        pass  # Skip for local

    async def _should_continue(self) -> bool:
        for full_id, flow in self._graphs.get_ready_with_meta():
            if await flow.is_local(full_id[-1]):
                return True  # Has local action
            if (
                await flow.is_action(full_id[-1])
                and full_id not in self._tasks_mgr.started
            ):
                return True  # Has unchecked batch action
        return False

    async def _finish_run(self, attempt_status: TaskStatus) -> None:
        # Only process failures during local run
        if attempt_status != TaskStatus.SUCCEEDED:
            await super()._finish_run(attempt_status)
