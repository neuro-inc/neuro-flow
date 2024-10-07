import asyncio
import logging
import os
import shlex
import sys
import textwrap
from apolo_sdk import (
    BadGateway,
    Client,
    ClientError,
    DiskVolume,
    EnvParseResult,
    HTTPPort,
    JobDescription,
    JobRestartPolicy,
    JobStatus,
    Preset,
    RemoteImage,
    ResourceNotFound,
    SecretFile,
    ServerNotAvailable,
    Tag,
    Volume,
    VolumeParseResult,
)
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
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
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
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
from .storage.base import (
    Attempt,
    AttemptStorage,
    Bake,
    BakeImage,
    BakeImageStorage,
    BakeStorage,
    ConfigsMeta,
    ProjectStorage,
    Storage,
    Task as StorageTask,
    TaskStatusItem,
    _Unset,
)
from .types import AlwaysT, FullID, ImageStatus, RemotePath, TaskStatus
from .utils import (
    TERMINATED_JOB_STATUSES,
    RetryConfig,
    fmt_id,
    fmt_raw_id,
    fmt_status,
    retries,
    retry,
)


log = logging.getLogger(__name__)


class NotFinished(ValueError):
    pass


async def get_running_flow(
    bake: Bake, client: Client, storage: BakeStorage, configs_meta: ConfigsMeta
) -> RunningBatchFlow:
    config_loader = BatchRemoteCL(
        configs_meta,
        client=client,
        bake_storage=storage,
    )
    local_info = LocallyPreparedInfo(
        children_info={},
        early_images={},
        git_info=bake.meta.git_info,
    )
    async for image in storage.list_bake_images():
        for yaml_def in image.yaml_defs:
            *prefix, image_id = yaml_def
            sub = local_info
            for part in prefix:
                if part not in sub.children_info:
                    new_sub = LocallyPreparedInfo(
                        children_info={},
                        early_images={},
                        git_info=bake.meta.git_info,
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
                dockerfile_rel=(
                    RemotePath(image.dockerfile_rel) if image.dockerfile_rel else None
                ),
            )
    return await RunningBatchFlow.create(
        config_loader=config_loader,
        batch=bake.batch,
        bake_id=bake.id,
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
        log.debug(f"Graph: is_active check, self._ready={self._ready}")
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
        log.debug(f"Graph: marking node {node} with {level}")

        prefix, item = node[:-1], node[-1]
        assert prefix in self._topos, f"Parent graph for node {node} not found"
        topo = self._topos[prefix]
        if topo.is_colored(item, level):
            return

        if node in self._topos:
            assert node in self._ready_to_mark_embeds[level], (
                f"Node '{node}' cannot be marked to {level} when "
                f"embeded graph is not all marked with {level}"
            )
            self._ready_to_mark_embeds[level].remove(node)

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
        log.debug(f"Graph: embedding to node {node} graph {graph}")
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
        self._tasks: Dict[FullID, StorageTask] = {}

    @property
    def tasks(self) -> Mapping[FullID, StorageTask]:
        return self._tasks

    def list_unfinished_raw_tasks(self) -> Iterable[Tuple[StorageTask, str]]:
        for task in self._tasks.values():
            if not task.status.is_finished and task.raw_id:
                yield task, task.raw_id

    def update(self, task: StorageTask) -> None:
        self._tasks[task.yaml_id] = task

    def count_unfinished(self, prefix: FullID = ()) -> int:
        def _with_prefix(full_id: FullID) -> bool:
            return all(x == y for x, y in zip(prefix, full_id))

        return sum(
            1
            for v in self._tasks.values()
            if v.raw_id and _with_prefix(v.yaml_id) and not v.status.is_finished
        )

    def build_needs(self, prefix: FullID, deps: AbstractSet[str]) -> NeedsCtx:
        needs = {}
        for dep_id in deps:
            full_id = prefix + (dep_id,)
            dep = self._tasks.get(full_id)
            if dep is None or not dep.status.is_finished:
                raise NotFinished(full_id)
            assert dep.outputs is not None
            status = TaskStatus(dep.status)
            if status == TaskStatus.CACHED:
                status = TaskStatus.SUCCEEDED
            needs[dep_id] = DepCtx(status, dep.outputs)
        return needs

    def build_state(self, prefix: FullID, state_from: Optional[str]) -> StateCtx:
        if state_from is None:
            return {}
        full_id = prefix + (state_from,)
        dep = self._tasks.get(full_id)
        if dep is None or not dep.status.is_finished:
            raise NotFinished(full_id)
        assert dep.state is not None
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
    log.debug(f"start_image_build: executing {cmd}")
    subprocess = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert subprocess.stdout
    assert subprocess.stderr
    stdout = ""
    while subprocess.returncode is None:
        log.debug(f"start_image_build: reading line...")
        line = (await subprocess.stdout.readline()).decode()
        log.debug(f"start_image_build: read line: {line}")
        stdout += line
        if line.startswith("Job ID: "):
            # Job is started, we can freely kill apolo-cli
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
        project_name: Optional[str] = None,
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
            project_name=project_name,
        )

    @retry
    async def job_status(self, raw_id: str) -> JobDescription:
        return await self._client.jobs.status(raw_id)

    async def job_logs(self, raw_id: str) -> AsyncIterator[bytes]:
        processed_bytes = 0
        for attempt in retries(
            f"job_logs({raw_id!r})",
            timeout=self._retry_timeout,
            delay=self._delay,
            factor=self._delay_factor,
            cap=self._delay_cap,
            exceptions=(ClientError, ServerNotAvailable, BadGateway, OSError),
        ):
            async with attempt:
                left = 0
                async for chunk in self._client.jobs.monitor(raw_id):
                    chunk_len = len(chunk)
                    if left == processed_bytes:
                        # yield the whole chunk
                        yield chunk
                        processed_bytes += chunk_len
                        left = processed_bytes
                    elif left + chunk_len <= processed_bytes:
                        # skip the whole chunk
                        left += chunk_len
                    else:
                        # yield a partial chunk
                        yield chunk[processed_bytes - left :]
                        processed_bytes += chunk_len
                        left = processed_bytes
                return
        assert False, "Unreachable"

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


class BatchExecutor:
    transient_progress: bool = False
    run_builder_job: Callable[..., Awaitable[str]] = staticmethod(  # type: ignore
        start_image_build
    )

    def __init__(
        self,
        console: Console,
        flow: RunningBatchFlow,
        bake: Bake,
        attempt: Attempt,
        client: RetryReadNeuroClient,
        storage: AttemptStorage,
        bake_storage: BakeStorage,
        project_storage: ProjectStorage,
        *,
        polling_timeout: Optional[float] = 1,
        project_role: Optional[str] = None,
    ) -> None:
        self._progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[progress.remaining]{task.elapsed:.0f} sec"),
            console=console,
            auto_refresh=False,
            transient=self.transient_progress,
            redirect_stderr=True,
        )
        self._top_flow = flow
        self._bake = bake
        self._attempt = attempt
        self._client = client
        self._storage = storage
        self._project_storage = project_storage
        self._bake_storage = bake_storage
        self._graphs: Graph[RunningBatchBase[BaseBatchContext]] = Graph(
            flow.graph, flow
        )
        self._tasks_mgr = BakeTasksManager()
        self._is_cancelling = False
        self._project_role = project_role

        self._run_builder_job = self.run_builder_job

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
        bake_id: str,
        client: Client,
        storage: Storage,
        *,
        polling_timeout: Optional[float] = 1,
        project_role: Optional[str] = None,
    ) -> AsyncIterator["BatchExecutor"]:
        storage = storage.with_retry_read()

        console.log("Fetch bake data")
        bake_storage = storage.bake(id=bake_id)
        bake = await bake_storage.get()
        if bake.last_attempt:
            attempt = bake.last_attempt
            attempt_storage = bake_storage.attempt(id=bake.last_attempt.id)
        else:
            attempt_storage = bake_storage.last_attempt()
            attempt = await attempt_storage.get()

        console.log("Fetch configs metadata")
        flow = await get_running_flow(bake, client, bake_storage, attempt.configs_meta)

        console.log(f"Execute attempt #{attempt.number}")

        ret = cls(
            console=console,
            flow=flow,
            bake=bake,
            attempt=attempt,
            client=RetryReadNeuroClient(client),
            storage=attempt_storage,
            bake_storage=bake_storage,
            project_storage=storage.project(id=bake.project_id),
            polling_timeout=polling_timeout,
            project_role=project_role,
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
        self._attempt = await self._storage.get()

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

    def _advance_progress_bar(
        self, old_task: Optional[StorageTask], task: StorageTask
    ) -> None:
        def _state_to_progress(status: TaskStatus) -> int:
            if status.is_pending:
                return 1
            if status.is_running:
                return 2
            return 3

        if old_task:
            advance = _state_to_progress(task.status) - _state_to_progress(
                old_task.status
            )
        else:
            advance = _state_to_progress(task.status)
        progress_bar_id = self._bars[task.yaml_id[:-1]]
        self._progress.update(progress_bar_id, advance=advance, refresh=True)

    def _update_graph_coloring(self, task: StorageTask) -> None:
        if task.status.is_running or task.status.is_finished:
            self._graphs.mark_running(task.yaml_id)
        if task.status.is_finished:
            self._graphs.mark_done(task.yaml_id)

    async def _log_task_status_change(self, task: StorageTask) -> None:
        flow = self._graphs.get_meta(task.yaml_id)
        in_flow_id = task.yaml_id[-1]
        if await flow.is_action(in_flow_id):
            log_args = ["Action"]
        elif await flow.is_local(in_flow_id):
            log_args = ["Local action"]
        else:
            log_args = ["Task"]
        log_args.append(fmt_id(task.yaml_id))
        if task.raw_id:
            log_args.append(fmt_raw_id(task.raw_id))
        log_args += ["is", fmt_status(task.status)]
        if task.status.is_finished:
            if task.outputs:
                log_args += ["with following outputs:"]
            else:
                log_args += ["(no outputs)"]
        self._progress.log(*log_args)
        if task.outputs:
            for key, value in task.outputs.items():
                self._progress.log(f"  {key}: {value}")

    async def _create_task(
        self,
        yaml_id: FullID,
        raw_id: Optional[str],
        status: Union[TaskStatusItem, TaskStatus],
        outputs: Optional[Mapping[str, str]] = None,
        state: Optional[Mapping[str, str]] = None,
    ) -> StorageTask:
        task = await self._storage.create_task(yaml_id, raw_id, status, outputs, state)
        self._advance_progress_bar(None, task)
        self._update_graph_coloring(task)
        await self._log_task_status_change(task)
        self._tasks_mgr.update(task)
        return task

    async def _update_task(
        self,
        yaml_id: FullID,
        *,
        outputs: Union[Optional[Mapping[str, str]], Type[_Unset]] = _Unset,
        state: Union[Optional[Mapping[str, str]], Type[_Unset]] = _Unset,
        new_status: Optional[Union[TaskStatusItem, TaskStatus]] = None,
    ) -> StorageTask:
        old_task = self._tasks_mgr.tasks[yaml_id]
        task = await self._storage.task(id=old_task.id).update(
            outputs=outputs,
            state=state,
            new_status=new_status,
        )
        self._advance_progress_bar(old_task, task)
        self._update_graph_coloring(task)
        await self._log_task_status_change(task)
        self._tasks_mgr.update(task)
        return task

    # New tasks processers

    async def _skip_task(self, full_id: FullID) -> None:
        log.debug(f"BatchExecutor: skipping task {full_id}")
        await self._create_task(
            yaml_id=full_id,
            status=TaskStatus.SKIPPED,
            raw_id=None,
            outputs={},
            state={},
        )

    async def _process_local(self, full_id: FullID) -> None:
        raise ValueError("Processing of local actions is not supported")

    async def _process_action(self, full_id: FullID) -> None:
        log.debug(f"BatchExecutor: processing action {full_id}")
        await self._create_task(
            yaml_id=full_id,
            status=TaskStatus.PENDING,
            raw_id=None,
        )
        await self._embed_action(full_id)

    async def _process_task(self, full_id: FullID) -> None:
        log.debug(f"BatchExecutor: processing task {full_id}")
        task = await self._get_task(full_id)

        # Check is task fits max_parallel
        for n in range(1, len(full_id) + 1):
            node = full_id[:n]
            prefix = node[:-1]
            if self._tasks_mgr.count_unfinished(prefix) >= task.strategy.max_parallel:
                return

        cache_strategy = task.cache.strategy
        storage_task: Optional[StorageTask] = None
        if cache_strategy == ast.CacheStrategy.DEFAULT:
            try:
                cache_entry = await self._project_storage.cache_entry(
                    task_id=full_id, batch=self._bake.batch, key=task.caching_key
                ).get()
            except ResourceNotFound:
                pass
            else:
                now = datetime.now(timezone.utc)
                eol = cache_entry.created_at + timedelta(task.cache.life_span)
                if now < eol:
                    storage_task = await self._create_task(
                        yaml_id=full_id,
                        raw_id=cache_entry.raw_id,
                        status=TaskStatus.CACHED,
                        outputs=cache_entry.outputs,
                        state=cache_entry.state,
                    )

        if storage_task is None:
            await self._start_task(full_id, task)

    async def _load_previous_run(self) -> None:
        log.debug(f"BatchExecutor: loading previous run")
        # Loads tasks that previous executor run processed.
        # Do not handles fail fast option.

        root_id = ()
        task_id = self._progress.add_task(
            f"<{self._bake.batch}>",
            completed=0,
            total=self._graphs.get_size(root_id) * 3,
        )
        self._bars[root_id] = task_id

        tasks = {task.yaml_id: task async for task in self._storage.list_tasks()}

        def _set_task_info(task: StorageTask) -> None:
            self._update_graph_coloring(task)
            self._advance_progress_bar(None, task)
            self._tasks_mgr.update(task)

        # Rebuild data in graph and task_mgr
        while tasks.keys() != self._tasks_mgr.tasks.keys():
            log.debug(f"BatchExecutor: rebuilding data...")
            for full_id, ctx in self._graphs.get_ready_with_meta():
                if full_id not in tasks or full_id in self._tasks_mgr.tasks:
                    continue
                task = tasks[full_id]
                if await ctx.is_action(full_id[-1]):
                    await self._embed_action(full_id)
                    if task.status.is_pending:
                        _set_task_info(task)
                else:
                    _set_task_info(task)
            for full_id in self._graphs.get_ready_to_mark_running_embeds():
                task = tasks[full_id]
                if task.status.is_finished:
                    self._graphs.mark_running(full_id)
                elif task.status.is_running:
                    _set_task_info(task)
            for full_id in self._graphs.get_ready_to_mark_done_embeds():
                task = tasks[full_id]
                if task.status.is_finished:
                    _set_task_info(task)

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
            await self._storage.update(
                executor_id=job_id,
            )

        if self._attempt.result.is_finished:
            # If attempt is already terminated, just clean up tasks
            # and exit
            await self._cancel_unfinished()
            return self._attempt.result

        await self._storage.update(
            result=TaskStatus.RUNNING,
        )

        while await self._should_continue():
            _mgr = self._tasks_mgr

            def _fmt_debug(task: StorageTask) -> str:
                return ".".join(task.yaml_id) + f" - {task.status}"

            log.debug(
                f"BatchExecutor: main loop start:\n"
                f"tasks={', '.join(_fmt_debug(it) for it in _mgr.tasks.values())}\n"
            )
            for full_id, flow in self._graphs.get_ready_with_meta():
                tid = full_id[-1]
                if full_id in self._tasks_mgr.tasks:
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

            await asyncio.sleep(self._polling_timeout or 0)

        return self._accumulate_result()

    async def _finish_run(self, attempt_status: TaskStatus) -> None:
        if not self._attempt.result.is_finished:
            await self._storage.update(result=attempt_status)
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
                f"[b]apolo-flow restart {self._bake.id}[/b]"
            )

    async def _cancel_unfinished(self) -> None:
        self._is_cancelling = True
        for task, raw_id in self._tasks_mgr.list_unfinished_raw_tasks():
            task_ctx = await self._get_task(task.yaml_id)
            if task_ctx.enable is not AlwaysT():
                self._progress.log(f"Task {fmt_id(task.yaml_id)} is being killed")
                await self._client.job_kill(raw_id)
        async for image in self._bake_storage.list_bake_images():
            if image.status == ImageStatus.BUILDING:
                assert image.builder_job_id
                await self._client.job_kill(image.builder_job_id)

    async def _store_to_cache(self, task: StorageTask) -> None:
        log.debug(f"BatchExecutor: storing to cache {task.yaml_id}")
        task_ctx = await self._get_task(task.yaml_id)
        cache_strategy = task_ctx.cache.strategy
        if (
            cache_strategy == ast.CacheStrategy.NONE
            or task.status != TaskStatus.SUCCEEDED
            or task.raw_id is None
            or task.outputs is None
            or task.state is None
        ):
            return

        await self._project_storage.create_cache_entry(
            key=task_ctx.caching_key,
            batch=self._bake.batch,
            task_id=task.yaml_id,
            raw_id=task.raw_id,
            outputs=task.outputs,
            state=task.state,
        )

    async def _process_started(self) -> bool:
        log.debug(f"BatchExecutor: processing started")
        # Process tasks
        for task, raw_id in self._tasks_mgr.list_unfinished_raw_tasks():
            assert task.raw_id, "list_unfinished_raw_tasks should list raw tasks"
            job_descr = await self._client.job_status(task.raw_id)
            log.debug(
                f"BatchExecutor: got description {job_descr} for task {task.yaml_id}"
            )
            if (
                job_descr.status in {JobStatus.RUNNING, JobStatus.SUCCEEDED}
                and task.status.is_pending
            ):
                assert (
                    job_descr.history.started_at
                ), "RUNNING jobs should have started_at"
                task = await self._update_task(
                    task.yaml_id,
                    new_status=TaskStatusItem(
                        when=job_descr.history.started_at,
                        status=TaskStatus.RUNNING,
                    ),
                )
            if job_descr.status in TERMINATED_JOB_STATUSES:
                log.debug(f"BatchExecutor: processing logs for task {task.yaml_id}")
                async with CmdProcessor() as proc:
                    async for chunk in self._client.job_logs(raw_id):
                        async for line in proc.feed_chunk(chunk):
                            pass
                    async for line in proc.feed_eof():
                        pass
                log.debug(
                    f"BatchExecutor: finished processing logs for task {task.yaml_id}"
                )
                assert (
                    job_descr.history.finished_at
                ), "TERMINATED jobs should have finished_at"
                task = await self._update_task(
                    task.yaml_id,
                    new_status=TaskStatusItem(
                        when=job_descr.history.finished_at,
                        status=TaskStatus(job_descr.status),
                    ),
                    outputs=proc.outputs,
                    state=proc.states,
                )
                await self._store_to_cache(task)
                task_meta = await self._get_meta(task.yaml_id)
                if task.status != TaskStatus.SUCCEEDED and task_meta.strategy.fail_fast:
                    return False
        # Process batch actions
        for full_id in self._graphs.get_ready_to_mark_running_embeds():
            log.debug(f"BatchExecutor: marking action {full_id} as ready")
            await self._update_task(full_id, new_status=TaskStatus.RUNNING)

        for full_id in self._graphs.get_ready_to_mark_done_embeds():
            log.debug(f"BatchExecutor: marking action {full_id} as done")
            # done action, make it finished
            ctx = await self._get_action(full_id)
            results = self._tasks_mgr.build_needs(full_id, ctx.graph.keys())
            res_ctx = await ctx.calc_outputs(results)

            task = await self._update_task(
                full_id,
                new_status=TaskStatus(res_ctx.result),
                outputs=res_ctx.outputs,
                state={},
            )

            task_id = self._bars[full_id]
            self._progress.remove_task(task_id)

            task_meta = await self._get_meta(full_id)
            if task.status != TaskStatus.SUCCEEDED and task_meta.strategy.fail_fast:
                return False
        return True

    def _accumulate_result(self) -> TaskStatus:
        for task in self._tasks_mgr.tasks.values():
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

    async def _start_task(self, full_id: FullID, task: Task) -> Optional[StorageTask]:
        log.debug(f"BatchExecutor: checking should we build image for {full_id}")
        remote_image = self._client.parse_remote_image(task.image)
        log.debug(f"BatchExecutor: image name is {remote_image}")
        if remote_image.cluster_name is None:  # Not a platform registry image
            return await self._run_task(full_id, task)

        image_storage = self._bake_storage.bake_image(ref=task.image)
        try:
            bake_image = await image_storage.get()
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
            if bake_image.status == ImageStatus.PENDING:
                await image_storage.update(
                    status=ImageStatus.CACHED,
                )
            return await self._run_task(full_id, task)

        if bake_image.status == ImageStatus.PENDING:
            await self._start_image_build(bake_image, image_ctx, image_storage)
            return None  # wait for next pulling interval
        elif bake_image.status == ImageStatus.BUILDING:
            return None  # wait for next pulling interval
        else:
            # Image is already build (maybe with an error, just try to run a job)
            return await self._run_task(full_id, task)

    async def _run_task(self, full_id: FullID, task: Task) -> StorageTask:
        log.debug(f"BatchExecutor: starting job for {full_id}")
        preset_name = task.preset
        if preset_name is None:
            preset_name = next(iter(self._client.config_presets))

        envs = self._client.parse_envs([f"{k}={v}" for k, v in task.env.items()])

        volumes_parsed = self._client.parse_volumes(task.volumes)
        volumes = list(volumes_parsed.volumes)

        http_auth = task.http_auth
        if http_auth is None:
            http_auth = HTTPPort.requires_auth

        restart_policy = JobRestartPolicy.NEVER
        if task.restart:
            restart_policy = JobRestartPolicy(task.restart)

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
            restart_policy=restart_policy,
            project_name=self._top_flow.project_name,
        )
        return await self._create_task(
            yaml_id=full_id,
            raw_id=job.id,
            status=TaskStatusItem(
                when=job.history.created_at or datetime.now(timezone.utc),
                status=TaskStatus.PENDING,
            ),
        )

    async def _start_image_build(
        self,
        bake_image: BakeImage,
        image_ctx: ImageCtx,
        image_storage: BakeImageStorage,
    ) -> None:
        log.debug(f"BatchExecutor: starting image build for {bake_image}")
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

        cmd = ["apolo-extras", "image", "build"]
        cmd.append(f"--project={self._top_flow.project_name}")
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
        if image_ctx.extra_kaniko_args is not None:
            cmd.append(
                f"--extra-kaniko-args={shlex.quote(image_ctx.extra_kaniko_args)}"
            )
        cmd.append(str(context))
        cmd.append(str(bake_image.ref))
        builder_job_id = await self._run_builder_job(*cmd)
        await image_storage.update(
            builder_job_id=builder_job_id,
            status=ImageStatus.BUILDING,
        )
        self._progress.log("Image", fmt_id(bake_image.ref), "is", ImageStatus.BUILDING)
        self._progress.log("  builder job:", fmt_raw_id(builder_job_id))

    async def _process_running_builds(self) -> None:
        log.debug(f"BatchExecutor: checking running build")
        async for image in self._bake_storage.list_bake_images():
            log.debug(f"BatchExecutor: processing image {image}")
            image_storage = self._bake_storage.bake_image(id=image.id)
            if image.status == ImageStatus.BUILDING:
                assert image.builder_job_id
                descr = await self._client.job_status(image.builder_job_id)
                log.debug(f"BatchExecutor: got job description {descr}")
                if descr.status == JobStatus.SUCCEEDED:
                    await image_storage.update(
                        status=ImageStatus.BUILT,
                    )
                    self._progress.log(
                        "Image", fmt_id(image.ref), "is", ImageStatus.BUILT
                    )
                elif descr.status in TERMINATED_JOB_STATUSES:
                    await image_storage.update(
                        status=ImageStatus.BUILD_FAILED,
                    )
                    self._progress.log(
                        "Image", fmt_id(image.ref), "is", ImageStatus.BUILD_FAILED
                    )


class LocalsBatchExecutor(BatchExecutor):
    transient_progress = True

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        console: Console,
        bake_id: str,
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
            bake_id,
            client,
            storage,
            polling_timeout=0,
            project_role=project_role,
        ) as ret:
            yield ret

    async def _process_local(self, full_id: FullID) -> None:
        local = await self._get_local(full_id)
        task = await self._create_task(
            yaml_id=full_id,
            status=TaskStatus.PENDING,
            raw_id=None,
        )
        posix = False if sys.platform == "win32" else True
        subprocess = await asyncio.create_subprocess_exec(
            *shlex.split(local.cmd, posix=posix),
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
        task = await self._update_task(
            task.yaml_id,
            new_status=result_status,
            outputs=proc.outputs,
            state={},
        )

    async def _process_task(self, full_id: FullID) -> None:
        pass  # Skip for local

    async def _should_continue(self) -> bool:
        for full_id, flow in self._graphs.get_ready_with_meta():
            if await flow.is_local(full_id[-1]):
                return True  # Has local action
            if (
                await flow.is_action(full_id[-1])
                and full_id not in self._tasks_mgr.tasks
            ):
                return True  # Has unchecked batch action
        return False

    async def _finish_run(self, attempt_status: TaskStatus) -> None:
        # Only process failures during local run
        if attempt_status != TaskStatus.SUCCEEDED:
            await super()._finish_run(attempt_status)
