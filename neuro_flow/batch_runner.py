import dataclasses

import click
import datetime
import neuro_extras
import neuromation
import sys
from graphviz import Digraph
from neuromation.api import Client, ResourceNotFound
from operator import attrgetter, itemgetter
from rich import box
from rich.console import Console
from rich.table import Table
from types import TracebackType
from typing import AbstractSet, Dict, List, Mapping, Optional, Tuple, Type
from typing_extensions import AsyncContextManager, AsyncIterator

import neuro_flow

from .batch_executor import BatchExecutor, ExecutorData, LocalsBatchExecutor
from .commands import CmdProcessor
from .config_loader import BatchLocalCL
from .context import EMPTY_ROOT, EarlyBatch, RunningBatchFlow
from .parser import ConfigDir
from .storage import Attempt, Bake, FinishedTask, Storage
from .types import FullID, LocalPath, TaskStatus
from .utils import TERMINATED_TASK_STATUSES, fmt_datetime, run_subproc


if sys.version_info >= (3, 9):
    import graphlib
else:
    from . import backport_graphlib as graphlib

EXECUTOR_IMAGE = f"neuromation/neuro-flow:{neuro_flow.__version__}"


GRAPH_COLORS = {
    TaskStatus.PENDING: "skyblue",
    TaskStatus.RUNNING: "steelblue",
    TaskStatus.SUCCEEDED: "limegreen",
    TaskStatus.CANCELLED: "orange",
    TaskStatus.SKIPPED: "magenta",
    TaskStatus.FAILED: "orangered",
    TaskStatus.UNKNOWN: "crimson",
}


class BatchRunner(AsyncContextManager["BatchRunner"]):
    def __init__(
        self,
        config_dir: ConfigDir,
        console: Console,
        client: Client,
        storage: Storage,
    ) -> None:
        self._config_dir = config_dir
        self._console = console
        self._client = client
        self._storage = storage
        self._config_loader: Optional[BatchLocalCL] = None
        self._project: Optional[str] = None

    @property
    def project(self) -> str:
        assert self._project is not None
        return self._project

    @property
    def config_loader(self) -> BatchLocalCL:
        assert self._config_loader is not None
        return self._config_loader

    async def close(self) -> None:
        if self._config_loader is not None:
            await self._config_loader.close()

    async def __aenter__(self) -> "BatchRunner":
        self._config_loader = BatchLocalCL(self._config_dir)
        project_ast = await self._config_loader.fetch_project()
        self._project = await project_ast.id.eval(EMPTY_ROOT)
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    # Next function is also used in tests:
    async def _setup_exc_data(
        self, batch_name: str, params: Optional[Mapping[str, str]] = None
    ) -> ExecutorData:
        # batch_name is a name of yaml config inside self._workspace / .neuro
        # folder without the file extension
        self._console.print(f"[bright_black]neuromation=={neuromation.__version__}")
        self._console.print(f"[bright_black]neuro-extras=={neuro_extras.__version__}")
        self._console.print(f"[bright_black]neuro-flow=={neuro_flow.__version__}")
        self._console.print(
            f"Use config file {self.config_loader.flow_path(batch_name)}"
        )

        self._console.print("Check config... ", end="")

        # Check that the yaml is parseable
        flow = await RunningBatchFlow.create(self.config_loader, batch_name, params)

        for volume in flow.volumes.values():
            if volume.local is not None:
                # TODO: sync volumes if needed
                raise NotImplementedError("Volumes sync is not supported")

        graphs = await self._build_graphs(flow)

        self._console.print("[green]ok")

        self._console.print("Create bake")
        config_meta, configs = await self.config_loader.collect_configs(batch_name)
        bake = await self._storage.create_bake(
            flow.project_id,
            batch_name,
            config_meta,
            configs,
            graphs=graphs,
            params=params,
        )
        self._console.print(
            f"Bake [b]{bake.bake_id}[/b] of project [b]{bake.project}[/b] is created"
        )

        return ExecutorData(
            project=bake.project,
            batch=bake.batch,
            when=bake.when,
            suffix=bake.suffix,
        )

    async def _build_graphs(
        self, top_flow: RunningBatchFlow
    ) -> Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]]:
        graphs = {}
        to_check: List[Tuple[FullID, EarlyBatch]] = [((), top_flow)]
        while to_check:
            prefix, flow = to_check.pop(0)
            graph = flow.graph
            graphs[prefix] = {
                prefix + (key,): {prefix + (node,) for node in nodes}
                for key, nodes in graph.items()
            }

            # check fast for the graph cycle error
            toposorter = graphlib.TopologicalSorter(graph)
            toposorter.prepare()

            for tid in graph:
                if await flow.is_action(tid):
                    sub_flow = await flow.get_action_early(tid)
                    to_check.append((prefix + (tid,), sub_flow))
        return graphs

    # Next function is also used in tests:
    async def _run_locals(
        self,
        data: ExecutorData,
    ) -> None:
        executor = await LocalsBatchExecutor.create(
            self._console,
            data,
            self._client,
            self._storage,
        )
        await executor.run()

    async def bake(
        self,
        batch_name: str,
        local_executor: bool = False,
        params: Optional[Mapping[str, str]] = None,
    ) -> None:
        data = await self._setup_exc_data(batch_name, params)
        await self._run_bake(data, local_executor)

    async def _run_bake(self, data: ExecutorData, local_executor: bool) -> None:
        await self._run_locals(data)
        if local_executor:
            self._console.print(f"[bright_black]Using local executor")
            await self.process(data)
        else:
            self._console.print(f"[bright_black]Starting remote executor")
            param = data.serialize()
            await run_subproc(
                "neuro",
                "run",
                # TODO: re-enable restarting following issue is fixed:
                # https://github.com/neuro-inc/platform-client-python/issues/1797
                # "--restart=on-failure",
                "--pass-config",
                EXECUTOR_IMAGE,
                "neuro-flow",
                "--fake-workspace",
                "execute",
                param,
            )

    async def process(
        self,
        data: ExecutorData,
    ) -> None:
        executor = await BatchExecutor.create(
            self._console, data, self._client, self._storage
        )
        await executor.run()

    def get_bakes(self) -> AsyncIterator[Bake]:
        return self._storage.list_bakes(self.project)

    async def get_bake_attempt(self, bake_id: str, *, attempt_no: int = -1) -> Attempt:
        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        return await self._storage.find_attempt(bake, attempt_no)

    async def list_bakes(self) -> None:
        table = Table(box=box.MINIMAL_HEAVY_HEAD)
        table.add_column("ID", style="bold")
        table.add_column("STATUS")
        table.add_column("WHEN")

        rows: List[Tuple[str, TaskStatus, datetime.datetime]] = []
        async for bake in self._storage.list_bakes(self.project):
            try:
                attempt = await self._storage.find_attempt(bake)
            except ValueError:
                self._console.print(
                    f"[yellow]Bake [b]{bake}[/b] is malformed, skipping"
                )
            else:
                rows.append((bake.bake_id, attempt.result, attempt.when))

        # sort by date, ascending order (last is bottommost)
        rows.sort(key=itemgetter(2))

        for row in rows:
            bake_id, result, when = row
            table.add_row(bake_id, result, fmt_datetime(when))
        self._console.print(table)

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
        table = Table(box=box.MINIMAL_HEAVY_HEAD)
        table.add_column("ID", style="bold")
        table.add_column("STATUS")
        table.add_column("RAW ID", style="bright_black")
        table.add_column("STARTED")
        table.add_column("FINISHED")

        try:
            bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        except ResourceNotFound:
            self._console.print("[yellow]Bake not found")
            self._console.print(
                "Please make sure that the bake [b]{bake_id}[/b] and "
                f"project [b]{self.project}[/b] are correct."
            )
            exit(1)

        attempt = await self._storage.find_attempt(bake, attempt_no)

        self._console.print(f"[b]Attempt #{attempt.number}[/b]", attempt.result)

        started, finished = await self._storage.fetch_attempt(attempt)
        statuses = {}
        for task in sorted(started.values(), key=attrgetter("when")):
            task_id = task.id
            raw_id = task.raw_id
            finished_task = finished.get(task_id)
            if finished_task:
                table.add_row(
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
                table.add_row(
                    ".".join(task_id),
                    statuses[task_id],
                    raw_id,
                    fmt_datetime(task.when),
                    fmt_datetime(None),
                )

        self._console.print(table)

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
                color = GRAPH_COLORS[status]
            elif task_id in statuses:
                color = GRAPH_COLORS[statuses[task_id]]
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
        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
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
        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
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

    async def clear_cache(self, batch: Optional[str] = None) -> None:
        await self._storage.clear_cache(self.project, batch)

    async def restart(
        self,
        bake_id: str,
        *,
        attempt_no: int = -1,
        from_failed: bool = True,
        local_executor: bool = False,
    ) -> None:
        data = await self._restart(
            bake_id, attempt_no=attempt_no, from_failed=from_failed
        )
        await self._run_bake(data, local_executor)

    async def _restart(
        self,
        bake_id: str,
        *,
        attempt_no: int = -1,
        from_failed: bool = True,
    ) -> ExecutorData:
        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        attempt = await self._storage.find_attempt(bake, attempt_no)
        if attempt.result not in TERMINATED_TASK_STATUSES:
            raise click.BadArgumentUsage(
                f"Cannot re-run still running attempt #{attempt.number} "
                f"of {bake.bake_id}."
            )
        if attempt.number >= 99:
            raise click.BadArgumentUsage(
                f"Cannot re-run {bake.bake_id}, the number of attempts exceeded."
            )
        new_att = await self._storage.create_attempt(bake, attempt.number + 1)
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
        return data
