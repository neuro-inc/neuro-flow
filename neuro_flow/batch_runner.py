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
from .batch_executor import BatchExecutor, LocalsBatchExecutor, get_running_flow
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
from .storage.base import (
    Attempt,
    Bake,
    BakeImage,
    BakeMeta,
    BakeStorage,
    ProjectStorage,
    Storage,
)
from .types import FullID, LocalPath, TaskStatus
from .utils import (
    CommandRunner,
    GlobalOptions,
    collect_git_info,
    encode_global_options,
    fmt_datetime,
    fmt_timedelta,
    make_cmd_exec,
)


EXECUTOR_IMAGE = f"ghcr.io/neuro-inc/neuro-flow:{neuro_flow.__version__}"


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
    neuro_runner: CommandRunner,
    storage: BakeStorage,
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
        self._project_storage: Optional[ProjectStorage] = None
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

    @property
    def storage(self) -> ProjectStorage:
        assert self._project_storage is not None
        return self._project_storage

    async def close(self) -> None:
        if self._config_loader is not None:
            await self._config_loader.close()

    async def __aenter__(self) -> "BatchRunner":
        self._config_loader = BatchLocalCL(self._config_dir, self._client)
        self._project = await setup_project_ctx(EMPTY_ROOT, self._config_loader)
        project = await self._storage.get_or_create_project(self._project.id)
        self._project_storage = self._storage.project(id=project.id)
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
    ) -> Tuple[Bake, RunningBatchFlow]:
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

        bake = await self.storage.create_bake(
            batch=batch_name,
            graphs=graphs,
            params=flow.params,
            name=name,
            tags=tags,
            meta=BakeMeta(
                git_info=await collect_git_info(),
            ),
        )
        bake_storage = self.storage.bake(id=bake.id)
        config_meta = await self.config_loader.collect_configs(batch_name, bake_storage)
        await bake_storage.create_attempt(number=1, configs_meta=config_meta)

        self._console.log(
            f"Bake [b]{bake.name or bake.id}[/b] of "
            f"project [b]{self.project_id}[/b] is created"
        )
        self._console.log("Uploading image contexts/dockerfiles...")
        await upload_image_data(flow, self._run_neuro_cli, bake_storage)

        return bake, flow

    # Next function is also used in tests:
    async def _run_locals(
        self,
        bake_id: str,
    ) -> TaskStatus:
        async with LocalsBatchExecutor.create(
            self._console,
            bake_id,
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
        bake, flow = await self._setup_bake(batch_name, params, name, tags)
        await self._run_bake(bake, flow, local_executor)

    async def _run_bake(
        self,
        bake: Bake,
        flow: RunningBatchFlow,
        local_executor: bool,
    ) -> None:
        self._console.rule("Run local actions")
        locals_result = await self._run_locals(bake.id)
        if locals_result != TaskStatus.SUCCEEDED:
            return
        self._console.rule("Run main actions")
        if local_executor:
            self._console.log(f"[bright_black]Using local executor")
            await self.process(bake.id)
        else:
            self._console.log(f"[bright_black]Starting remote executor")
            if flow.life_span:
                life_span = fmt_timedelta(flow.life_span)
            else:
                life_span = "7d"
            run_args = [
                "run",
                "--pass-config",
                f"--volume=storage:.flow/logs/{bake.id}/:/root/.neuro/logs"
                f"--life-span={life_span}",
                f"--tag=project:{self.project_id}",
                f"--tag=flow:{bake.batch}",
                f"--tag=bake_id:{bake.id}",
                f"--tag=remote_executor",
            ]
            project_role = self.project_role
            if project_role is not None:
                run_args.append(f"--share={project_role}")
            run_args += [
                EXECUTOR_IMAGE,
                "--",
                "neuro-flow",
                *encode_global_options(self._global_options),
                "--fake-workspace",
                "execute",
                bake.id,
            ]
            await self._run_neuro_cli(*run_args)

    async def process(
        self,
        bake_id: str,
    ) -> None:
        async with BatchExecutor.create(
            self._console,
            bake_id,
            self._client,
            self._storage,
            project_role=self.project_role,
        ) as executor:
            status = await executor.run()
            if status != TaskStatus.SUCCEEDED:
                raise BakeFailedError(status)

    def get_bakes(self) -> AsyncIterator[Bake]:
        return self.storage.list_bakes()

    async def get_bake_attempt(self, bake_id: str, *, attempt_no: int = -1) -> Attempt:
        return await self._storage.bake(id=bake_id).attempt(number=attempt_no).get()

    async def list_bakes(
        self,
        tags: AbstractSet[str] = frozenset(),
        since: Optional[datetime.datetime] = None,
        until: Optional[datetime.datetime] = None,
        recent_first: bool = False,
    ) -> None:
        def _setup_table() -> Table:
            table = Table(box=box.MINIMAL_HEAVY_HEAD)
            table.add_column(
                "ID",
                style="bold",
                width=len("bake-f6bd815b-3a3b-4ea1-b5ec-e8ab13678e3e"),
            )
            table.add_column("NAME", min_width=12)
            table.add_column("BATCH", min_width=20)
            table.add_column(
                "EXECUTOR", width=len("job-f6bd815b-3a3b-4ea1-b5ec-e8ab13678e3e")
            )
            table.add_column("STATUS", width=9)
            table.add_column("WHEN", min_width=10)
            table.show_edge = False
            return table

        header_table = _setup_table()
        self._console.print(header_table)

        async for bake in self.storage.list_bakes(
            tags=tags,
            since=since,
            until=until,
            recent_first=recent_first,
        ):
            if bake.last_attempt is None:
                self._console.print(
                    f"[yellow]Bake [b]{bake.id}[/b] is malformed, skipping"
                )
            else:
                row_table = _setup_table()
                row_table.show_header = False
                row_table.add_row(
                    bake.id,
                    bake.name or "",
                    bake.batch,
                    bake.last_attempt.executor_id or "",
                    bake.last_attempt.result,
                    fmt_datetime(bake.last_attempt.created_at),
                )
                self._console.print(row_table)

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

        bake_storage = self.storage.bake(id=bake_id)
        try:
            bake = await bake_storage.get()
        except ResourceNotFound:
            self._console.print("[yellow]Bake not found")
            self._console.print(
                f"Please make sure that the bake [b]{bake_id}[/b] and "
                f"project [b]{self.project_id}[/b] are correct."
            )
            exit(1)
            assert False, "unreachable"

        attempt_storage = bake_storage.attempt(number=attempt_no)
        attempt = await attempt_storage.get()

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

        tasks = [task async for task in attempt_storage.list_tasks()]

        for task in sorted(tasks, key=attrgetter("created_at")):
            task_table.add_row(
                ".".join(task.yaml_id),
                task.status,
                task.raw_id,
                fmt_datetime(task.created_at),
                fmt_datetime(task.finished_at),
            )

        self._console.print("Tasks:")
        self._console.print(task_table)

        image_table = Table(box=box.MINIMAL_HEAVY_HEAD)
        image_table.add_column("REF", style="bold")
        image_table.add_column("STATUS")
        image_table.add_column("BUILDER ID", style="bright_black")
        async for image in bake_storage.list_bake_images():
            image_table.add_row(
                image.ref,
                image.status,
                image.builder_job_id or "",
            )
        if image_table.rows:
            self._console.print("Images:")
            self._console.print(image_table)

        if output is None:
            output = LocalPath(f"{bake.id}_{attempt.number}").with_suffix(".gv")

        graphs = bake.graphs
        dot = Digraph(bake.batch, filename=str(output), strict=True, engine="dot")
        dot.attr(compound="true")
        dot.node_attr = {"style": "filled"}

        await self._subgraph(
            dot, graphs, (), {}, {task.yaml_id: task.status for task in tasks}
        )

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

            if task_id in statuses:
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
        attempt_storage = self.storage.bake(id=bake_id).attempt(number=attempt_no)
        attempt = await attempt_storage.get()
        full_id = tuple(task_id.split("."))
        try:
            task = await attempt_storage.task(yaml_id=full_id).get()
        except ResourceNotFound:
            raise click.BadArgumentUsage(f"Unknown task {task_id}")

        if not task.status.is_finished:
            raise click.BadArgumentUsage(f"Task {task_id} is not finished")

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
        attempt_storage = self.storage.bake(id=bake_id).attempt(number=attempt_no)
        attempt = await attempt_storage.get()
        if attempt.result.is_finished:
            raise click.BadArgumentUsage(
                f"Attempt #{attempt.number} of {attempt.bake_id} is already stopped."
            )
        await attempt_storage.update(result=TaskStatus.CANCELLED)
        self._console.print(
            f"[b]Attempt #{attempt.number}[/b] of bake "
            f"[b]{attempt.bake_id}[/b] was cancelled."
        )

    async def clear_cache(
        self, batch: Optional[str] = None, task_id: Optional[str] = None
    ) -> None:
        full_id: Optional[FullID] = None
        if task_id:
            full_id = tuple(task_id.split("."))
        await self.storage.delete_cache_entries(batch, full_id)

    async def restart(
        self,
        bake_id: str,
        *,
        attempt_no: int = -1,
        from_failed: bool = True,
        local_executor: bool = False,
    ) -> None:
        bake, flow = await self._restart(
            bake_id, attempt_no=attempt_no, from_failed=from_failed
        )
        await self._run_bake(bake, flow, local_executor)

    async def _restart(
        self,
        bake_id: str,
        *,
        attempt_no: int = -1,
        from_failed: bool = True,
    ) -> Tuple[Bake, RunningBatchFlow]:
        bake_storage = self.storage.bake(id=bake_id)
        bake = await bake_storage.get()
        if bake.last_attempt and attempt_no == -1:
            last_attempt = attempt = bake.last_attempt
        else:
            attempt = await bake_storage.attempt(number=attempt_no).get()
            last_attempt = await bake_storage.last_attempt().get()
        if not attempt.result.is_finished:
            raise click.BadArgumentUsage(
                f"Cannot re-run still running attempt #{attempt.number} "
                f"of {bake.id}."
            )
        if not last_attempt.result.is_finished:
            raise click.BadArgumentUsage(
                f"Cannot re-run bake when last attempt #{last_attempt.number} "
                f"of {bake.id} is still running."
            )
        if attempt.result == TaskStatus.SUCCEEDED and from_failed:
            raise click.BadArgumentUsage(
                f"Cannot re-run successful attempt #{attempt.number} "
                f"of {bake.id} with `--from-failed` flag set.\n"
                "Hint: Try adding --no-from-failed to restart bake from the beginning."
            )
        if attempt.number >= 99:
            raise click.BadArgumentUsage(
                f"Cannot re-run {bake.id}, the number of attempts exceeded."
            )
        new_attempt = await bake_storage.create_attempt(
            number=last_attempt.number + 1,
            configs_meta=attempt.configs_meta,
        )
        if from_failed:
            new_attempt_storage = bake_storage.attempt(id=new_attempt.id)
            graphs = bake.graphs
            handled = set()  # a set of succesfully finished and not cached tasks
            tasks = {
                task.yaml_id: task
                async for task in bake_storage.attempt(id=attempt.id).list_tasks()
            }
            for task in sorted(tasks.values(), key=attrgetter("created_at")):
                if task.status == TaskStatus.SUCCEEDED:
                    # should check deps to don't process post-actions with
                    # always() precondition
                    prefix = task.yaml_id[:-1]
                    graph = graphs[prefix]
                    deps = graph[task.yaml_id]
                    if not deps or all(dep in handled for dep in deps):
                        if (
                            prefix in tasks
                            and tasks[prefix].status != TaskStatus.SUCCEEDED
                        ):
                            # If action didn't succeeded, we should create task manually
                            await new_attempt_storage.create_task(
                                yaml_id=prefix,
                                status=TaskStatus.PENDING,
                                raw_id=None,
                            )
                        # TODO allow to create task with multiple statuses
                        # and copy them from old task
                        await new_attempt_storage.create_task(
                            yaml_id=task.yaml_id,
                            status=TaskStatus.SUCCEEDED,
                            raw_id=task.raw_id,
                            outputs=task.outputs,
                            state=task.state,
                        )
                        handled.add(task.id)

        self._console.print(f"[b]Attempt #{new_attempt.number}[/b] is created")
        flow = await get_running_flow(
            bake, self._client, bake_storage, new_attempt.configs_meta
        )

        return bake, flow
