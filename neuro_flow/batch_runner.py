import asyncio
import click
import sys
from graphviz import Digraph
from neuromation.api import Client, JobStatus
from neuromation.cli.formatters import ftable  # TODO: extract into a separate library
from types import TracebackType
from typing import Dict, List, Optional, Sequence, Type, Union
from typing_extensions import AsyncContextManager, AsyncIterator

from . import __version__, ast
from .batch_executor import BatchExecutor, ExecutorData
from .commands import CmdProcessor
from .context import EMPTY_ROOT, BatchContext, DepCtx, TaskContext
from .parser import ConfigDir, parse_action, parse_batch, parse_project
from .storage import Attempt, Bake, BatchStorage, ConfigFile
from .types import LocalPath, TaskStatus
from .utils import TERMINATED_JOB_STATUSES, fmt_id, fmt_raw_id, fmt_status


if sys.version_info >= (3, 9):
    import graphlib
else:
    from . import backport_graphlib as graphlib

EXECUTOR_IMAGE = f"neuromation/neuro-flow:{__version__}"


class BatchRunner(AsyncContextManager["BatchRunner"]):
    def __init__(
        self, config_dir: ConfigDir, client: Client, storage: BatchStorage
    ) -> None:
        self._config_dir = config_dir
        self._client = client
        self._storage = storage
        self._project: Optional[str] = None

    @property
    def project(self) -> str:
        assert self._project is not None
        return self._project

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "BatchRunner":
        project_file = self._config_dir.workspace / "project.yml"
        if project_file.exists():
            pr = parse_project(project_file)
            self._project = await pr.id.eval(EMPTY_ROOT)
        else:
            self._project = self._config_dir.workspace.name
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    def _parse_action_name(self, action_name: str) -> LocalPath:
        scheme, sep, spec = action_name.partition(":")
        if not sep:
            raise ValueError(f"{action_name} has no schema")
        if scheme in ("ws", "workspace"):
            path = self._config_dir.workspace / spec
            if not path.exists():
                path = path.with_suffix(".yml")
            if not path.exists():
                raise ValueError(f"Action {action_name} does not exist")
            return path
        else:
            raise ValueError(f"Unsupported scheme '{scheme}'")

    async def _collect_configs_for_task(
        self, tasks: Sequence[Union[ast.Task, ast.TaskActionCall]]
    ) -> List[LocalPath]:
        result: List[LocalPath] = []
        for task in tasks:
            if isinstance(task, ast.BaseActionCall):
                action_name = await task.action.eval(EMPTY_ROOT)
                action_path = self._parse_action_name(action_name)
                result += [LocalPath(action_path)]
                result += await self._collect_subaction_configs(
                    parse_action(action_path)
                )
        return result

    async def _collect_subaction_configs(
        self, action: ast.BaseAction
    ) -> List[LocalPath]:
        if isinstance(action, ast.BatchAction):
            return await self._collect_configs_for_task(action.tasks)
        else:
            return []

    async def _collect_additional_configs(self, flow: ast.BatchFlow) -> List[LocalPath]:
        result = []
        project_file = self._config_dir.workspace / "project.yml"
        if project_file.exists():
            result = [project_file]
        return result + await self._collect_configs_for_task(flow.tasks)

    async def bake(self, batch_name: str, local_executor: bool = False) -> None:
        # batch_name is a name of yaml config inside self._workspace / .neuro
        # folder without the file extension
        config_file = (self._config_dir.config_dir / (batch_name + ".yml")).resolve()

        click.echo(f"Use config file {config_file}")

        click.echo("Check config... ", nl=False)
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

        configs = [config_file, *await self._collect_additional_configs(flow)]
        configs_files = [
            ConfigFile(
                path.relative_to(self._config_dir.workspace),
                path.read_text(),
            )
            for path in configs
        ]

        click.echo("ok")

        click.echo("Create bake")
        bake = await self._storage.create_bake(
            self.project,
            batch_name,
            config_file.name,
            configs_files,
        )
        click.echo(f"Bake {fmt_id(str(bake))} is created")

        data = ExecutorData(
            project=bake.project,
            batch=bake.batch,
            when=bake.when,
            suffix=bake.suffix,
        )
        if local_executor:
            click.echo(f"Using local executor")
            await self.process(data)
        else:
            click.echo(f"Starting remove executor")
            param = data.serialize()
            await self._run_subproc(
                "neuro",
                "run",
                "--restart=on-failure",
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
        executor = BatchExecutor(data, self._client, self._storage)
        await executor.run()

    def get_bakes(self) -> AsyncIterator[Bake]:
        return self._storage.list_bakes(self.project)

    async def get_bake_attempt(self, bake_id: str, *, attempt_no: int = -1) -> Attempt:
        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        return await self._storage.find_attempt(bake, attempt_no)

    async def list_bakes(self) -> None:
        rows: List[List[str]] = []
        async for bake in self._storage.list_bakes(self.project):
            try:
                attempt = await self._storage.find_attempt(bake)
            except ValueError:
                click.secho(f"Bake {bake} is malformed, skipping", fg="yellow")
            else:
                rows.append([fmt_id(bake.bake_id), fmt_status(attempt.result)])

        rows.sort()

        rows.insert(0, [click.style("ID", bold=True), click.style("Status", bold=True)])
        for line in ftable.table(rows):
            click.echo(line)

    async def inspect(self, bake_id: str, *, attempt_no: int = -1) -> None:
        rows: List[List[str]] = []
        rows.append(
            [
                click.style("ID", bold=True),
                click.style("Status", bold=True),
                click.style("Raw ID", bold=True),
            ]
        )

        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        attempt = await self._storage.find_attempt(bake, attempt_no)

        click.echo(
            " ".join(
                [
                    fmt_id(f"Attempt #{attempt.number}"),
                    fmt_status(attempt.result),
                ]
            )
        )

        started, finished, skipped = await self._storage.fetch_attempt(attempt)
        for task in started.values():
            task_id = task.id
            raw_id = task.raw_id
            if task_id in finished:
                rows.append(
                    [
                        fmt_id(task_id),
                        fmt_status(finished[task_id].status),
                        fmt_raw_id(raw_id),
                    ]
                )
            elif task_id in skipped:
                rows.append([fmt_id(task_id), fmt_status(JobStatus.CANCELLED), ""])
            elif task_id in started:
                info = await self._client.jobs.status(raw_id)
                rows.append(
                    [fmt_id(task_id), fmt_status(info.status.value), fmt_raw_id(raw_id)]
                )
            else:
                # Unreachable currently
                rows.append(
                    [fmt_id(task_id), fmt_status(JobStatus.UNKNOWN), ""],
                )

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
                    fmt_id(f"Attempt #{attempt.number}"),
                    fmt_status(attempt.result),
                ]
            )
        )
        click.echo(
            " ".join(
                [
                    (f"Task {fmt_id(task_id)}"),
                    fmt_status(task.status),
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

    async def cancel(self, bake_id: str, *, attempt_no: int = -1) -> None:
        bake = await self._storage.fetch_bake_by_id(self.project, bake_id)
        attempt = await self._storage.find_attempt(bake, attempt_no)
        if attempt.result in TERMINATED_JOB_STATUSES:
            raise click.BadArgumentUsage(f"This bake attempt is already stopped.")
        await self._storage.finish_attempt(attempt, JobStatus.CANCELLED)
        click.echo(f"Attempt #{attempt.number} of bake {bake.bake_id} was cancelled.")

    async def _run_subproc(self, exe: str, *args: str) -> None:
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

    async def clear_cache(self, batch: Optional[str] = None) -> None:
        await self._storage.clear_cache(self.project, batch)

    async def graph(self, batch_name: str, output: Optional[LocalPath]) -> None:
        config_file = (self._config_dir.config_dir / (batch_name + ".yml")).resolve()
        flow = parse_batch(self._config_dir.workspace, config_file)
        assert isinstance(flow, ast.BatchFlow)
        ctx = await BatchContext.create(flow, self._config_dir.workspace, config_file)
        if output is None:
            output = batch_name + ".gv"
        dot = Digraph(batch_name, filename=str(output), strict=True, engine="dot")
        dot.attr(compound="true")

        await self._subgraph(dot, ctx, {})
        click.echo(f"Saving file {dot.filename}")
        dot.save()
        click.echo(f"Open {dot.filename}.pdf")
        dot.view()

    async def _subgraph(
        self, dot: Digraph, ctx: TaskContext, anchors: Dict[str, str]
    ) -> None:
        first = True
        for task_id, deps in ctx.graph.items():
            tgt = ".".join(task_id)
            name = task_id[-1]

            if first:
                anchors[".".join(ctx.prefix)] = tgt
                first = False

            needs = {
                key: DepCtx(TaskStatus.SUCCEEDED, {}) for key in ctx.get_dep_ids(name)
            }
            if await ctx.is_action(name):
                lhead = "cluster_" + tgt
                with dot.subgraph(name=lhead) as subdot:
                    action_ctx = await ctx.with_action(name, needs=needs)
                    subdot.attr(label=f"{name} [{action_ctx.action}]")
                    subdot.attr(compound="true")
                    await self._subgraph(subdot, action_ctx, anchors)
                tgt = anchors[tgt]
            else:
                # task_ctx = await ctx.with_task(name, needs=needs)
                dot.node(tgt, name)
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
