import dataclasses

import click
import datetime
import neuro_extras
from collections import defaultdict
from graphviz import Digraph
from neuro_cli import __version__ as cli_version
from neuro_sdk import Client, ResourceNotFound, __version__ as sdk_version
from operator import attrgetter
from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from types import TracebackType
from typing import (
    AbstractSet,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    cast,
)
from typing_extensions import AsyncContextManager, AsyncIterator
from yarl import URL

import neuro_flow

from . import ast
from .batch_executor import (
    BatchExecutor,
    ExecutorData,
    LocalsBatchExecutor,
    get_running_flow,
)
from .colored_topo_sorter import ColoredTopoSorter
from .commands import CmdProcessor
from .config_loader import BatchLocalCL
from .context import (
    EMPTY_ROOT,
    EarlyBatch,
    EarlyLocalCall,
    ProjectCtx,
    RunningBatchFlow,
    setup_project_ctx,
)
from .expr import EvalError, MultiError
from .parser import ConfigDir
from .storage import Attempt, Bake, BakeImage, FinishedTask, Storage
from .types import FullID, LocalPath, TaskStatus
from .utils import (
    TERMINATED_TASK_STATUSES,
    CommandRunner,
    GlobalOptions,
    encode_global_options,
    fmt_datetime,
    fmt_timedelta,
    make_cmd_exec,
)


EXECUTOR_IMAGE = f"neuromation/neuro-flow:{neuro_flow.__version__}"


GRAPH_COLORS = {
    TaskStatus.PENDING: "skyblue",
    TaskStatus.RUNNING: "steelblue",
    TaskStatus.SUCCEEDED: "limegreen",
    TaskStatus.CANCELLED: "orange",
    TaskStatus.SKIPPED: "magenta",
    TaskStatus.CACHED: "yellowgreen",
    TaskStatus.FAILED: "orangered",
    TaskStatus.UNKNOWN: "crimson",
}


class BakeFailedError(Exception):
    def __init__(self, status: TaskStatus):
        self.status = status


async def iter_flows(top_flow: EarlyBatch) -> AsyncIterator[Tuple[FullID, EarlyBatch]]:
    to_check: List[Tuple[FullID, EarlyBatch]] = [((), top_flow)]
    while to_check:
        prefix, flow = to_check.pop(0)
        yield prefix, flow
        for tid in flow.graph:
            if await flow.is_action(tid):
                sub_flow = await flow.get_action_early(tid)
                to_check.append((prefix + (tid,), sub_flow))


async def check_no_cycles(top_flow: EarlyBatch) -> None:
    async for _, flow in iter_flows(top_flow):
        ColoredTopoSorter(flow.graph)


async def check_local_deps(top_flow: EarlyBatch) -> None:
    # This methods works in O(kn^3), where:
    # - n is number of tasks in the flow
    # - k is maximal depths of actions
    # This complexity is because:
    # For each task (n) for task's each dependency (n) and for each remote task (n)
    # do prefix check (k). Note that task are ofter have a few dependencies,
    # so in real cases one of those n effectively const.
    #
    # If performance becomes a problem, it can be replaced
    # with Trie (prefix tree) to reduce time complexity to O(kn^2)
    # (for each task (n) for each task's dependency (n) do Trie check (k))

    runs_on_remote: Set[FullID] = set()

    async for prefix, flow in iter_flows(top_flow):
        runs_on_remote.update(
            {prefix + (tid,) for tid in flow.graph if await flow.is_task(tid)}
        )

    def _is_prefix(item: FullID, prefix: FullID) -> bool:
        if len(item) < len(prefix):
            return False
        return all(x == y for (x, y) in zip(item, prefix))

    def _remote_deps(prefix: FullID, deps: Iterable[str]) -> Iterable[FullID]:
        return (
            remote
            for dep in deps
            for remote in runs_on_remote
            if _is_prefix(remote, prefix + (dep,))
        )

    async for prefix, flow in iter_flows(top_flow):
        early_locals = cast(
            AsyncIterator[EarlyLocalCall],
            (
                await flow.get_local_early(tid)
                for tid in flow.graph
                if await flow.is_local(tid)
            ),
        )
        with_bad_deps = (
            (early_local, remote)
            async for early_local in early_locals
            for remote in _remote_deps(prefix, early_local.needs)
        )
        async for early_local, remote in with_bad_deps:
            early_local_str = ".".join(prefix + (early_local.real_id,))
            remote_str = ".".join(remote)
            raise Exception(
                f"Local action '{early_local_str}' depends on remote "
                f"task '{remote_str}'. This is not supported because "
                "all local action should succeed before "
                "remote executor starts."
            )


async def check_expressions(top_flow: RunningBatchFlow) -> None:
    errors: List[EvalError] = []
    async for _, flow in iter_flows(top_flow):
        errors += flow.validate_expressions()
    if errors:
        raise MultiError(errors)


class ImageRefNotUniqueError(Exception):
    @dataclasses.dataclass
    class ImageInfo:
        context: Optional[Union[URL, LocalPath]]
        dockerfile: Optional[Union[URL, LocalPath]]
        ast: ast.Image

    def __init__(self, ref: str, images: Sequence[ImageInfo]) -> None:
        self._ref = ref
        self._images = images

    def __str__(self) -> str:
        return (
            f"Image with ref '{self._ref}' defined multiple times "
            f"with different attributes:\n"
            + "\n".join(
                f"at {EvalError.format_pos(image.ast._start)} with params:\n"
                f"  context: {image.context or '<empty>'}\n"
                f"  dockerfile: {image.dockerfile or '<empty>'}"
                for image in self._images
            )
        )


async def check_image_refs_unique(top_flow: RunningBatchFlow) -> None:
    _tmp: Dict[str, List[ImageRefNotUniqueError.ImageInfo]] = defaultdict(list)

    async for _, flow in iter_flows(top_flow):
        for image in flow.early_images.values():
            if image.ref.startswith("image:"):
                _tmp[image.ref].append(
                    ImageRefNotUniqueError.ImageInfo(
                        context=image.context,
                        dockerfile=image.dockerfile,
                        ast=flow.get_image_ast(image.id),
                    )
                )

    errors = []
    for ref, images in _tmp.items():
        contexts_differ = len({it.context for it in images}) > 1
        dockerfiles_differ = len({it.dockerfile for it in images}) > 1
        if contexts_differ or dockerfiles_differ:
            errors.append(ImageRefNotUniqueError(ref, images))
    if errors:
        raise MultiError(errors)


async def build_graphs(
    top_flow: RunningBatchFlow,
) -> Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]]:
    graphs = {}

    async for prefix, flow in iter_flows(top_flow):
        graphs[prefix] = {
            prefix + (key,): {prefix + (node,) for node in nodes}
            for key, nodes in flow.graph.items()
        }

    return graphs


async def upload_image_data(
    top_flow: RunningBatchFlow,
    bake: Bake,
    neuro_runner: CommandRunner,
    storage: Storage,
) -> List[BakeImage]:
    @dataclasses.dataclass
    class _TmpData:
        context_on_storage: Optional[URL]
        dockerfile_rel: Optional[str]
        yaml_defs: List[FullID]

    _tmp: Dict[str, _TmpData] = {}

    async for prefix, flow in iter_flows(top_flow):
        for image in flow.early_images.values():
            if isinstance(image.context, LocalPath):
                # Reusing image ref between bakes introduces
                # race condition anyway, so we can safely use it
                # as remote context dir name
                storage_context_dir: Optional[URL] = URL(
                    f"storage:.flow/{top_flow.project_id}/{image.ref.replace(':', '/')}"
                )
            else:
                storage_context_dir = image.context

            dockerfile_rel = None
            if image.dockerfile_rel:
                dockerfile_rel = str(image.dockerfile_rel.as_posix())

            prev_entry = _tmp.get(image.ref)
            if prev_entry is not None:
                # Validation is done before
                prev_entry.yaml_defs.append(prefix + (image.id,))
            else:
                if isinstance(image.context, LocalPath):
                    await neuro_runner(
                        "mkdir",
                        "--parents",
                        str(storage_context_dir),
                    )
                    await neuro_runner(
                        "cp",
                        "--recursive",
                        "--update",
                        "--no-target-directory",
                        str(image.context),
                        str(storage_context_dir),
                    )
                _tmp[image.ref] = _TmpData(
                    yaml_defs=[prefix + (image.id,)],
                    context_on_storage=storage_context_dir,
                    dockerfile_rel=dockerfile_rel,
                )

    return [
        await storage.create_bake_image(
            bake=bake,
            ref=ref,
            yaml_defs=entry.yaml_defs,
            context_on_storage=entry.context_on_storage,
            dockerfile_rel=entry.dockerfile_rel,
        )
        for ref, entry in _tmp.items()
    ]


class BatchRunner(AsyncContextManager["BatchRunner"]):
    def __init__(
        self,
        config_dir: ConfigDir,
        console: Console,
        client: Client,
        storage: Storage,
        global_options: GlobalOptions,
        run_neuro_cli: Optional[CommandRunner] = None,
    ) -> None:
        self._config_dir = config_dir
        self._console = console
        self._client = client
        self._storage = storage
        self._config_loader: Optional[BatchLocalCL] = None
        self._project: Optional[ProjectCtx] = None
        self._run_neuro_cli = run_neuro_cli or make_cmd_exec(
            "neuro", global_options=encode_global_options(global_options)
        )
        self._global_options = global_options

    @property
    def project_id(self) -> str:
        assert self._project is not None
        return self._project.id

    @property
    def project_role(self) -> Optional[str]:
        assert self._project is not None
        return self._project.role

    @property
    def config_loader(self) -> BatchLocalCL:
        assert self._config_loader is not None
        return self._config_loader

    async def close(self) -> None:
        if self._config_loader is not None:
            await self._config_loader.close()

    async def __aenter__(self) -> "BatchRunner":
        self._config_loader = BatchLocalCL(self._config_dir, self._client)
        self._project = await setup_project_ctx(EMPTY_ROOT, self._config_loader)
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    # Next function is also used in tests:
    async def _setup_bake(
        self,
        batch_name: str,
        params: Optional[Mapping[str, str]] = None,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
    ) -> Tuple[ExecutorData, RunningBatchFlow]:
        # batch_name is a name of yaml config inside self._workspace / .neuro
        # folder without the file extension
        self._console.log(f"[bright_black]neuro_sdk=={sdk_version}")
        self._console.log(f"[bright_black]neuro_cli=={cli_version}")
        self._console.log(f"[bright_black]neuro-extras=={neuro_extras.__version__}")
        self._console.log(f"[bright_black]neuro-flow=={neuro_flow.__version__}")
        self._console.log(f"Use config file {self.config_loader.flow_path(batch_name)}")

        # Check that the yaml is parseable
        flow = await RunningBatchFlow.create(
            self.config_loader, batch_name, "fake-bake-id", params
        )

        for volume in flow.volumes.values():
            if volume.local is not None:
                # TODO: sync volumes if needed
                raise NotImplementedError("Volumes sync is not supported")

        await check_no_cycles(flow)
        await check_local_deps(flow)
        await check_expressions(flow)
        await check_image_refs_unique(flow)
        graphs = await build_graphs(flow)

        self._console.log(
            "Check config... [green]ok[/green]",
        )

        self._console.log("Create bake...")
        config_meta, configs = await self.config_loader.collect_configs(batch_name)
        await self._storage.ensure_project(flow.project_id)
        bake = await self._storage.create_bake(
            flow.project_id,
            batch_name,
            config_meta,
            configs,
            graphs=graphs,
            params=params,
            name=name,
            tags=tags,
        )
        self._console.log(
            f"Bake [b]{bake.bake_id}[/b] of project [b]{bake.project}[/b] is created"
        )
        self._console.log("Uploading image contexts/dockerfiles...")
        await upload_image_data(flow, bake, self._run_neuro_cli, self._storage)

        return (
            ExecutorData(
                project=bake.project,
                batch=bake.batch,
                when=bake.when,
                suffix=bake.suffix,
            ),
            flow,
        )

    # Next function is also used in tests:
    async def _run_locals(
        self,
        data: ExecutorData,
    ) -> TaskStatus:
        async with LocalsBatchExecutor.create(
            self._console,
            data,
            self._client,
            self._storage,
            project_role=self.project_role,
        ) as executor:
            return await executor.run()

    async def bake(
        self,
        batch_name: str,
        local_executor: bool = False,
        params: Optional[Mapping[str, str]] = None,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
    ) -> None:
        self._console.print(
            Panel(f"[bright_blue]Bake [b]{batch_name}[/b]", padding=1),
            justify="center",
        )
        data, flow = await self._setup_bake(batch_name, params, name, tags)
        await self._run_bake(data, flow, local_executor)

    async def _run_bake(
        self,
        data: ExecutorData,
        flow: RunningBatchFlow,
        local_executor: bool,
    ) -> None:
        self._console.rule("Run local actions")
        locals_result = await self._run_locals(data)
        if locals_result != TaskStatus.SUCCEEDED:
            return
        self._console.rule("Run main actions")
        if local_executor:
            self._console.log(f"[bright_black]Using local executor")
            await self.process(data)
        else:
            self._console.log(f"[bright_black]Starting remote executor")
            param = data.serialize()
            if flow.life_span:
                life_span = fmt_timedelta(flow.life_span)
            else:
                life_span = "7d"
            run_args = [
                "run",
                "--pass-config",
                f"--life-span={life_span}",
                f"--tag=project:{data.project}",
                f"--tag=flow:{data.batch}",
                f"--tag=bake_id:{data.get_bake_id()}",
                f"--tag=remote_executor",
            ]
            project_role = self.project_role
            if project_role is not None:
                run_args.append(f"--share={project_role}")
            run_args += [
                EXECUTOR_IMAGE,
                "neuro-flow",
                *encode_global_options(self._global_options),
                "--fake-workspace",
                "execute",
                param,
            ]
            await self._run_neuro_cli(*run_args)

    async def process(
        self,
        data: ExecutorData,
    ) -> None:
        async with BatchExecutor.create(
            self._console,
            data,
            self._client,
            self._storage,
            project_role=self.project_role,
        ) as executor:
            status = await executor.run()
            if status != TaskStatus.SUCCEEDED:
                raise BakeFailedError(status)

    def get_bakes(self) -> AsyncIterator[Bake]:
        return self._storage.list_bakes(self.project_id)

    async def get_bake_attempt(self, bake_id: str, *, attempt_no: int = -1) -> Attempt:
        bake = await self._storage.fetch_bake_by_id(self.project_id, bake_id)
        return await self._storage.find_attempt(bake, attempt_no)

    async def list_bakes(
        self,
        tags: AbstractSet[str] = frozenset(),
        since: Optional[datetime.datetime] = None,
        until: Optional[datetime.datetime] = None,
        recent_first: bool = False,
    ) -> None:
        table = Table(box=box.MINIMAL_HEAVY_HEAD)
        table.add_column("ID", style="bold")
        table.add_column("NAME")
        table.add_column("EXECUTOR")
        table.add_column("STATUS")
        table.add_column("WHEN")

        with Live(table, auto_refresh=False) as live:
            async for bake in self._storage.list_bakes(
                self.project_id,
                tags=tags,
                since=since,
                until=until,
                recent_first=recent_first,
            ):
                try:
                    attempt = await self._storage.find_attempt(bake)
                except ValueError:
                    live.console.print(
                        f"[yellow]Bake [b]{bake}[/b] is malformed, skipping"
                    )
                else:
                    table.add_row(
                        bake.bake_id,
                        bake.name or "",
                        attempt.executor_id or "",
                        attempt.result,
                        fmt_datetime(attempt.when),
                    )
                    live.refresh()

    async def inspect(
        self,
        bake_id: str,
        *,
        attempt_no: int = -1,
        output: Optional[LocalPath] = None,
        save_dot: bool = False,
        save_pdf: bool = False,
        view_pdf: bool = False,
    ) -> None:

        try:
            bake = await self._storage.fetch_bake_by_id(self.project_id, bake_id)
        except ResourceNotFound:
            self._console.print("[yellow]Bake not found")
            self._console.print(
                f"Please make sure that the bake [b]{bake_id}[/b] and "
                f"project [b]{self.project_id}[/b] are correct."
            )
            exit(1)

        attempt = await self._storage.find_attempt(bake, attempt_no)

        self._console.print(f"[b]Bake id: {bake_id}[/b]")
        self._console.print(f"[b]Attempt #{attempt.number}[/b]", attempt.result)
        if attempt.executor_id:
            info = await self._client.jobs.status(attempt.executor_id)
            self._console.print(
                f"[b]Executor {attempt.executor_id}[/b]", TaskStatus(info.status)
            )

        task_table = Table(box=box.MINIMAL_HEAVY_HEAD)
        task_table.add_column("ID", style="bold")
        task_table.add_column("STATUS")
        task_table.add_column("RAW ID", style="bright_black")
        task_table.add_column("STARTED")
        task_table.add_column("FINISHED")

        started, finished = await self._storage.fetch_attempt(attempt)
        statuses = {}
        for task in sorted(started.values(), key=attrgetter("when")):
            task_id = task.id
            raw_id = task.raw_id
            finished_task = finished.get(task_id)
            if finished_task:
                task_table.add_row(
                    ".".join(task_id),
                    finished_task.status,
                    raw_id,
                    fmt_datetime(task.when),
                    fmt_datetime(finished_task.when),
                )
            else:
                if raw_id:
                    info = await self._client.jobs.status(raw_id)
                    statuses[task_id] = TaskStatus(info.status)
                else:
                    statuses[task_id] = TaskStatus.RUNNING
                task_table.add_row(
                    ".".join(task_id),
                    statuses[task_id],
                    raw_id,
                    fmt_datetime(task.when),
                    fmt_datetime(None),
                )

        self._console.print("Tasks:")
        self._console.print(task_table)

        image_table = Table(box=box.MINIMAL_HEAVY_HEAD)
        image_table.add_column("REF", style="bold")
        image_table.add_column("STATUS")
        image_table.add_column("BUILDER ID", style="bright_black")
        async for image in self._storage.list_bake_images(bake):
            image_table.add_row(
                image.ref,
                image.status,
                image.builder_job_id or "",
            )
        if image_table.rows:
            self._console.print("Images:")
            self._console.print(image_table)

        if output is None:
            output = LocalPath(f"{bake.bake_id}_{attempt.number}").with_suffix(".gv")

        graphs = bake.graphs
        dot = Digraph(bake.batch, filename=str(output), strict=True, engine="dot")
        dot.attr(compound="true")
        dot.node_attr = {"style": "filled"}

        await self._subgraph(dot, graphs, (), {}, statuses, finished)

        if save_dot:
            self._console.print(f"Saving file {dot.filename}")
            dot.save()
        if save_pdf:
            self._console.print(f"Rendering {dot.filename}.pdf")
            dot.render(view=view_pdf)
        elif view_pdf:
            self._console.print(f"Opening {dot.filename}.pdf")
            dot.view()

    async def _subgraph(
        self,
        dot: Digraph,
        graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]],
        prefix: FullID,
        anchors: Dict[str, str],
        statuses: Dict[FullID, TaskStatus],
        finished: Dict[FullID, FinishedTask],
    ) -> None:
        lhead: Optional[str]
        ltail: Optional[str]
        color: Optional[str]
        first = True
        graph = graphs[prefix]
        for task_id, deps in graph.items():
            tgt = ".".join(task_id)
            name = task_id[-1]

            if first:
                anchors[".".join(prefix)] = tgt
                first = False

            if task_id in finished:
                status = finished[task_id].status
                color = GRAPH_COLORS.get(status)
            elif task_id in statuses:
                color = GRAPH_COLORS.get(statuses[task_id])
            else:
                color = None

            if task_id in graphs:
                lhead = "cluster_" + tgt
                with dot.subgraph(name=lhead) as subdot:
                    subdot.attr(label=f"{name}")
                    subdot.attr(compound="true")
                    subdot.attr(color=color)
                    await self._subgraph(
                        subdot,
                        graphs,
                        task_id,
                        anchors,
                        statuses,
                        finished,
                    )
                tgt = anchors[tgt]
            else:
                dot.node(tgt, name, color=color)
                lhead = None

            for dep in deps:
                src = ".".join(dep)
                if src in anchors:
                    # src is a subgraph
                    ltail = "cluster_" + src
                    src = anchors[src]
                else:
                    ltail = None
                dot.edge(src, tgt, ltail=ltail, lhead=lhead)

    async def logs(
        self, bake_id: str, task_id: str, *, attempt_no: int = -1, raw: bool = False
    ) -> None:
        bake = await self._storage.fetch_bake_by_id(self.project_id, bake_id)
        attempt = await self._storage.find_attempt(bake, attempt_no)
        started, finished = await self._storage.fetch_attempt(attempt)
        full_id = tuple(task_id.split("."))
        if full_id not in finished:
            if full_id not in started:
                raise click.BadArgumentUsage(f"Unknown task {task_id}")
            else:
                raise click.BadArgumentUsage(f"Task {task_id} is not finished")
        else:
            task = finished[full_id]

        self._console.print(f"[b]Attempt #{attempt.number}[/b]", attempt.result)
        self._console.print(f"Task [b]{task_id}[/b]", task.status)

        if not task.raw_id:
            return

        if raw:
            async for chunk in self._client.jobs.monitor(task.raw_id):
                self._console.print(chunk.decode("utf-8", "replace"), end="")
        else:
            async with CmdProcessor() as proc:
                async for chunk in self._client.jobs.monitor(task.raw_id):
                    async for line in proc.feed_chunk(chunk):
                        self._console.print(line.decode("utf-8", "replace"), end="")
                async for line in proc.feed_eof():
                    self._console.print(line.decode("utf-8", "replace"), end="")

    async def cancel(self, bake_id: str, *, attempt_no: int = -1) -> None:
        bake = await self._storage.fetch_bake_by_id(self.project_id, bake_id)
        attempt = await self._storage.find_attempt(bake, attempt_no)
        if attempt.result in TERMINATED_TASK_STATUSES:
            raise click.BadArgumentUsage(
                f"Attempt #{attempt.number} of {bake.bake_id} is already stopped."
            )
        await self._storage.finish_attempt(attempt, TaskStatus.CANCELLED)
        self._console.print(
            f"[b]Attempt #{attempt.number}[/b] of bake "
            f"[b]{bake.bake_id}[/b] was cancelled."
        )

    async def clear_cache(
        self, batch: Optional[str] = None, task_id: Optional[str] = None
    ) -> None:
        await self._storage.clear_cache(self.project_id, batch, task_id)

    async def restart(
        self,
        bake_id: str,
        *,
        attempt_no: int = -1,
        from_failed: bool = True,
        local_executor: bool = False,
    ) -> None:
        data, flow = await self._restart(
            bake_id, attempt_no=attempt_no, from_failed=from_failed
        )
        await self._run_bake(data, flow, local_executor)

    async def _restart(
        self,
        bake_id: str,
        *,
        attempt_no: int = -1,
        from_failed: bool = True,
    ) -> Tuple[ExecutorData, RunningBatchFlow]:
        bake = await self._storage.fetch_bake_by_id(self.project_id, bake_id)
        last_attempt = await self._storage.find_attempt(bake, -1)
        attempt = await self._storage.find_attempt(bake, attempt_no)
        if attempt.result not in TERMINATED_TASK_STATUSES:
            raise click.BadArgumentUsage(
                f"Cannot re-run still running attempt #{attempt.number} "
                f"of {bake.bake_id}."
            )
        if attempt.result == TaskStatus.SUCCEEDED and from_failed:
            raise click.BadArgumentUsage(
                f"Cannot re-run successful attempt #{attempt.number} "
                f"of {bake.bake_id} with `--from-failed` flag set.\n"
                "Hint: Try adding --no-from-failed to restart bake from the beginning."
            )
        if last_attempt.number >= 99:
            raise click.BadArgumentUsage(
                f"Cannot re-run {bake.bake_id}, the number of attempts exceeded."
            )
        new_att = await self._storage.create_attempt(bake, last_attempt.number + 1)
        if from_failed:
            graphs = bake.graphs
            handled = set()  # a set of succesfully finished and not cached tasks
            started, finished = await self._storage.fetch_attempt(attempt)
            for task in sorted(finished.values(), key=attrgetter("when")):
                if task.status == TaskStatus.SUCCEEDED:
                    # should check deps to don't process post-actions with
                    # always() precondition
                    prefix = task.id[:-1]
                    graph = graphs[prefix]
                    deps = graph[task.id]
                    if not deps or all(dep in handled for dep in deps):
                        if (
                            prefix in finished
                            and finished[prefix].status != TaskStatus.SUCCEEDED
                        ):
                            # If action did not succeeded, we should write started
                            await self._storage.write_start(
                                dataclasses.replace(started[prefix], attempt=new_att)
                            )
                        await self._storage.write_start(
                            dataclasses.replace(started[task.id], attempt=new_att)
                        )
                        await self._storage.write_finish(
                            dataclasses.replace(task, attempt=new_att)
                        )
                        handled.add(task.id)

        self._console.print(f"[b]Attempt #{new_att.number}[/b] is created")
        data = ExecutorData(
            project=bake.project,
            batch=bake.batch,
            when=bake.when,
            suffix=bake.suffix,
        )
        flow = await get_running_flow(bake, self._client, self._storage)

        return data, flow
