import dataclasses

import asyncio
import base64
import datetime
import json
import os
import sys
import textwrap
from collections import defaultdict
from neuro_sdk import (
    Action,
    Client,
    DiskVolume,
    EnvParseResult,
    HTTPPort,
    IllegalArgumentError,
    JobDescription,
    JobRestartPolicy,
    JobStatus,
    Permission,
    Preset,
    RemoteImage,
    ResourceNotFound,
    SecretFile,
    Tag,
    Volume,
    VolumeParseResult,
)
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskID, TextColumn
from typing import (
    AbstractSet,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
)
from yarl import URL

from . import ast
from .colored_topo_sorter import ColoredTopoSorter
from .commands import CmdProcessor
from .config_loader import BatchRemoteCL
from .context import (
    BaseBatchContext,
    DepCtx,
    EarlyImageCtx,
    ImageCtx,
    LocallyPreparedInfo,
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
from .storage import (
    Attempt,
    Bake,
    BakeImage,
    FinishedTask,
    RetryReadStorage,
    StartedTask,
    Storage,
    _dt2str,
)
from .types import AlwaysT, FullID, ImageStatus, RemotePath, TaskStatus
from .utils import (
    TERMINATED_JOB_STATUSES,
    TERMINATED_TASK_STATUSES,
    RetryConfig,
    fmt_id,
    fmt_raw_id,
    fmt_status,
    retry,
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
    local_info = LocallyPreparedInfo(
        children_info={},
        early_images={},
    )
    async for image in storage.list_bake_images(bake):
        for yaml_def in image.yaml_defs:
            *prefix, image_id = yaml_def
            sub = local_info
            for part in prefix:
                if part not in sub.children_info:
                    new_sub = LocallyPreparedInfo(
                        children_info={},
                        early_images={},
                    )
                    assert isinstance(sub.children_info, dict)
                    sub.children_info[part] = new_sub
                sub = sub.children_info[part]
            assert isinstance(sub.early_images, dict)
            dockerfile = None
            if image.context_on_storage and image.dockerfile_rel:
                dockerfile = image.context_on_storage / str(image.dockerfile_rel)
            sub.early_images[image_id] = EarlyImageCtx(
                id=image_id,
                ref=image.ref,
                context=image.context_on_storage,
                dockerfile=dockerfile,
                dockerfile_rel=RemotePath(image.dockerfile_rel)
                if image.dockerfile_rel
                else None,
            )
    return await RunningBatchFlow.create(
        config_loader=config_loader,
        batch=bake.batch,
        bake_id=bake.bake_id,
        params=bake.params,
        local_info=local_info,
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

    def get_graph_data(self, node: FullID) -> _T:
        return self._metas[node]

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


class ImageBuildCommandError(Exception):
    def __init__(self, exit_code: int, stdout: str, stderr: str) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self) -> str:
        return (
            f"Image builder command failed:\n"
            f"exit code: {self.exit_code}\n"
            f"stdout: \n{textwrap.indent(self.stdout, '  ')}\n"
            f"stderr: \n{textwrap.indent(self.stderr, '  ')}"
        )


async def start_image_build(*cmd: str) -> str:
    subprocess = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert subprocess.stdout
    assert subprocess.stderr
    stdout = ""
    while subprocess.returncode is None:
        line = (await subprocess.stdout.readline()).decode()
        stdout += line
        if line.startswith("Job ID: "):
            # Job is started, we can freely kill neuro-cli
            subprocess.terminate()
            return line[len("Job ID: ") :].strip()

    stdout += (await subprocess.stdout.read()).decode()
    stderr = (await subprocess.stderr.read()).decode()
    raise ImageBuildCommandError(
        exit_code=subprocess.returncode,
        stdout=stdout,
        stderr=stderr,
    )


class RetryReadNeuroClient(RetryConfig):
    def __init__(self, client: Client) -> None:
        super().__init__()
        self._client = client

    async def job_start(
        self,
        *,
        image: RemoteImage,
        preset_name: str,
        entrypoint: Optional[str] = None,
        command: Optional[str] = None,
        working_dir: Optional[str] = None,
        http: Optional[HTTPPort] = None,
        env: Optional[Mapping[str, str]] = None,
        volumes: Sequence[Volume] = (),
        secret_env: Optional[Mapping[str, URL]] = None,
        secret_files: Sequence[SecretFile] = (),
        disk_volumes: Sequence[DiskVolume] = (),
        tty: bool = False,
        shm: bool = False,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
        description: Optional[str] = None,
        pass_config: bool = False,
        wait_for_jobs_quota: bool = False,
        schedule_timeout: Optional[float] = None,
        restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER,
        life_span: Optional[float] = None,
        privileged: bool = False,
    ) -> JobDescription:
        return await self._client.jobs.start(
            image=image,
            preset_name=preset_name,
            entrypoint=entrypoint,
            command=command,
            working_dir=working_dir,
            http=http,
            env=env,
            volumes=volumes,
            secret_env=secret_env,
            secret_files=secret_files,
            disk_volumes=disk_volumes,
            tty=tty,
            shm=shm,
            name=name,
            tags=tags,
            description=description,
            pass_config=pass_config,
            wait_for_jobs_quota=wait_for_jobs_quota,
            schedule_timeout=schedule_timeout,
            restart_policy=restart_policy,
            life_span=life_span,
            privileged=privileged,
        )

    @retry
    async def job_status(self, raw_id: str) -> JobDescription:
        return await self._client.jobs.status(raw_id)

    @retry
    async def _job_logs(self, raw_id: str) -> List[bytes]:
        chunks = []
        async for chunk in self._client.jobs.monitor(raw_id):
            chunks.append(chunk)
        return chunks

    async def job_logs(self, raw_id: str) -> AsyncIterator[bytes]:
        for chunk in await self._job_logs(raw_id):
            yield chunk

    async def job_kill(self, raw_id: str) -> None:
        await self._client.jobs.kill(raw_id)

    @retry
    async def image_tag_info(self, remote_image: RemoteImage) -> Tag:
        return await self._client.images.tag_info(remote_image)

    def parse_remote_image(self, image: str) -> RemoteImage:
        return self._client.parse.remote_image(image)

    @property
    def config_presets(self) -> Mapping[str, Preset]:
        return self._client.config.presets

    def parse_envs(
        self, env: Sequence[str], env_file: Sequence[str] = ()
    ) -> EnvParseResult:
        return self._client.parse.envs(env, env_file)

    def parse_volumes(self, volume: Sequence[str]) -> VolumeParseResult:
        return self._client.parse.volumes(volume)

    async def user_add(self, role_name: str) -> None:
        await self._client.users.add(role_name)

    async def user_share(self, user: str, permission: Permission) -> Permission:
        return await self._client.users.share(user, permission)


class BatchExecutor:
    def __init__(
        self,
        console: Console,
        flow: RunningBatchFlow,
        attempt: Attempt,
        client: RetryReadNeuroClient,
        storage: Storage,
        *,
        polling_timeout: float = 1,
        transient_progress: bool = False,
        project_role: Optional[str] = None,
        run_builder_job: Callable[..., Awaitable[str]] = start_image_build,
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
        self._project_role = project_role
        self._is_projet_role_created = False

        self._run_builder_job = run_builder_job

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
        project_role: Optional[str] = None,
        run_builder_job: Callable[..., Awaitable[str]] = start_image_build,
    ) -> AsyncIterator["BatchExecutor"]:
        storage = RetryReadStorage(storage)

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
            RetryReadNeuroClient(client),
            storage,
            polling_timeout=polling_timeout,
            transient_progress=transient_progress,
            project_role=project_role,
            run_builder_job=run_builder_job,
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
        # TODO: Drop force_no_cache when storage is refactored
        self._attempt = await self._storage.find_attempt(
            self._attempt.bake,
            self._attempt.number,
            force_no_cache=True,
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

    async def _get_image(self, bake_image: BakeImage) -> Optional[ImageCtx]:
        actions = []
        full_id_to_image: Dict[FullID, ImageCtx] = {}
        for yaml_def in bake_image.yaml_defs:
            *prefix, image_id = yaml_def
            actions.append(".".join(prefix))
            try:
                flow = self._graphs.get_graph_data(tuple(prefix))
            except KeyError:
                pass
            else:
                full_id_to_image[yaml_def] = flow.images[image_id]
        image_ctx = None
        for _it in full_id_to_image.values():
            image_ctx = _it  # Return any context
            break
        if not all(image_ctx == it for it in full_id_to_image.values()):
            locations_str = "\n".join(
                f" - {'.'.join(full_id)}" for full_id in full_id_to_image.keys()
            )
            self._progress.log(
                f"[red]Warning:[/red] definitions for image with"
                f" ref [b]{bake_image.ref}[/b] differ:\n"
                f"{locations_str}"
            )
        if len(full_id_to_image.values()) == 0:
            actions_str = ", ".join(f"'{it}'" for it in actions)
            self._progress.log(
                f"[red]Warning:[/red] image with ref "
                f"[b]{bake_image.ref}[/b] is referred "
                + (
                    f"before action {actions_str} "
                    "that holds its definition was able to run"
                    if len(actions) == 1
                    else f"before actions {actions_str} "
                    "that hold its definition were able to run"
                )
            )
        return image_ctx

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
            if st:
                self._mark_started(st)
                self._progress.log(
                    "Task",
                    fmt_id(st.id),
                    fmt_raw_id(st.raw_id),
                    "is",
                    TaskStatus.PENDING,
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
                job_descr = await self._client.job_status(st.raw_id)
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
            await self._process_running_builds()

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
        if attempt_status != TaskStatus.SUCCEEDED:
            self._progress.log(
                "[blue b]Hint:[/blue b] you can restart bake starting "
                "from first failed task "
                "by the following command:\n"
                f"[b]neuro-flow restart {self._attempt.bake.bake_id}[/b]"
            )

    async def _cancel_unfinished(self) -> None:
        self._is_cancelling = True
        for full_id, st in self._tasks_mgr.unfinished_tasks.items():
            task = await self._get_task(full_id)
            if task.enable is not AlwaysT():
                self._progress.log(f"Task {fmt_id(st.id)} is being killed")
                await self._client.job_kill(st.raw_id)
        async for image in self._storage.list_bake_images(self._attempt.bake):
            if image.status == ImageStatus.BUILDING:
                assert image.builder_job_id
                await self._client.job_kill(image.builder_job_id)

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
            job_descr = await self._client.job_status(st.raw_id)
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
                    async for chunk in self._client.job_logs(st.raw_id):
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

    async def _is_image_in_registry(self, remote_image: RemoteImage) -> bool:
        try:
            await self._client.image_tag_info(remote_image)
        except ResourceNotFound:
            return False
        return True

    async def _start_task(self, full_id: FullID, task: Task) -> Optional[StartedTask]:
        remote_image = self._client.parse_remote_image(task.image)
        if remote_image.cluster_name is None:  # Not a neuro registry image
            return await self._run_task(full_id, task)
        try:
            bake_image = await self._storage.get_bake_image(
                self._attempt.bake, task.image
            )
        except ResourceNotFound:
            # Not defined in the bake
            return await self._run_task(full_id, task)

        image_ctx = await self._get_image(bake_image)
        if image_ctx is None:
            # The image referred before definition
            return await self._run_task(full_id, task)

        if not image_ctx.force_rebuild and await self._is_image_in_registry(
            remote_image
        ):
            return await self._run_task(full_id, task)

        if bake_image.status == ImageStatus.PENDING:
            await self._start_image_build(bake_image, image_ctx)
            return None  # wait for next pulling interval
        elif bake_image.status == ImageStatus.BUILDING:
            return None  # wait for next pulling interval
        else:
            # Image is already build (maybe with an error, just try to run a job)
            return await self._run_task(full_id, task)

    async def _run_task(self, full_id: FullID, task: Task) -> StartedTask:
        preset_name = task.preset
        if preset_name is None:
            preset_name = next(iter(self._client.config_presets))

        envs = self._client.parse_envs([f"{k}={v}" for k, v in task.env.items()])

        volumes_parsed = self._client.parse_volumes(task.volumes)
        volumes = list(volumes_parsed.volumes)

        http_auth = task.http_auth
        if http_auth is None:
            http_auth = HTTPPort.requires_auth

        job = await self._client.job_start(
            shm=True,
            tty=False,
            image=self._client.parse_remote_image(task.image),
            preset_name=preset_name,
            entrypoint=task.entrypoint,
            command=task.cmd,
            http=HTTPPort(task.http_port, http_auth) if task.http_port else None,
            env=envs.env,
            secret_env=envs.secret_env,
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
        await self._add_resource(job.uri)
        return await self._storage.start_task(self._attempt, full_id, job)

    async def _start_image_build(
        self, bake_image: BakeImage, image_ctx: ImageCtx
    ) -> None:
        context = bake_image.context_on_storage or image_ctx.context
        dockerfile_rel = bake_image.dockerfile_rel or image_ctx.dockerfile_rel

        if context is None or dockerfile_rel is None:
            if context is None and dockerfile_rel is None:
                error = "context and dockerfile not specified"
            elif context is None and dockerfile_rel is not None:
                error = "context not specified"
            else:
                error = "dockerfile not specified"
            raise Exception(f"Failed to build image '{bake_image.ref}': {error}")

        cmd = ["neuro-extras", "image", "build"]
        cmd.append(f"--file={dockerfile_rel}")
        for arg in image_ctx.build_args:
            cmd.append(f"--build-arg={arg}")
        for vol in image_ctx.volumes:
            cmd.append(f"--volume={vol}")
        for k, v in image_ctx.env.items():
            cmd.append(f"--env={k}={v}")
        if image_ctx.force_rebuild:
            cmd.append("--force-overwrite")
        if image_ctx.build_preset is not None:
            cmd.append(f"--preset={image_ctx.build_preset}")
        cmd.append(str(context))
        cmd.append(str(bake_image.ref))
        builder_job_id = await self._run_builder_job(*cmd)
        await self._storage.update_bake_image(
            self._attempt.bake,
            bake_image.ref,
            builder_job_id=builder_job_id,
            status=ImageStatus.BUILDING,
        )
        self._progress.log("Image", fmt_id(bake_image.ref), "is", ImageStatus.BUILDING)
        self._progress.log("  builder job:", fmt_raw_id(builder_job_id))

    async def _process_running_builds(self) -> None:
        async for image in self._storage.list_bake_images(self._attempt.bake):
            if image.status == ImageStatus.BUILDING:
                assert image.builder_job_id
                descr = await self._client.job_status(image.builder_job_id)
                if descr.status == JobStatus.SUCCEEDED:
                    await self._storage.update_bake_image(
                        self._attempt.bake,
                        image.ref,
                        status=ImageStatus.BUILT,
                    )
                    self._progress.log(
                        "Image", fmt_id(image.ref), "is", ImageStatus.BUILT
                    )
                elif descr.status in TERMINATED_JOB_STATUSES:
                    await self._storage.update_bake_image(
                        self._attempt.bake,
                        image.ref,
                        status=ImageStatus.BUILD_FAILED,
                    )
                    self._progress.log(
                        "Image", fmt_id(image.ref), "is", ImageStatus.BUILD_FAILED
                    )

    async def _create_project_role(self, project_role: str) -> None:
        if self._is_projet_role_created:
            return
        try:
            await self._client.user_add(project_role)
        except IllegalArgumentError as e:
            if "already exists" not in str(e):
                raise
        self._is_projet_role_created = True

    async def _add_resource(self, uri: URL) -> None:
        project_role = self._project_role
        if project_role is None:
            return
        await self._create_project_role(project_role)
        permission = Permission(uri, Action.WRITE)
        try:
            await self._client.user_share(project_role, permission)
        except ValueError:
            self._progress.log(f"[red]Cannot share [b]{uri!s}[/b]")


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
        project_role: Optional[str] = None,
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
            project_role=project_role,
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
