import click
import neuro_sdk
import signal
import sys
from datetime import datetime, timezone
from dateutil.parser import isoparse
from neuro_cli.parse_utils import parse_timedelta
from typing import List, Optional, Sequence, Tuple

from neuro_flow.batch_runner import BatchRunner
from neuro_flow.cli.click_types import BAKE, BATCH, BATCH_OR_ALL, BakeTaskType
from neuro_flow.cli.utils import argument, option, resolve_bake, wrap_async
from neuro_flow.storage.api import ApiStorage
from neuro_flow.types import LocalPath

from ..parser import parse_bake_meta
from ..storage.base import Storage
from .root import Root


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack


@click.command()
@option("--local-executor", is_flag=True, default=False, help="Run primary job locally")
@click.option(
    "-p",
    "--param",
    type=(str, str),
    multiple=True,
    help="Set params of the batch config",
)
@click.option(
    "-n",
    "--name",
    metavar="NAME",
    type=str,
    help="Optional bake name",
    default=None,
)
@click.option(
    "--meta-from-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    help="File with params for batch.",
)
@click.option(
    "-t",
    "--tag",
    metavar="TAG",
    type=str,
    help="Optional bake tag, multiple values allowed",
    multiple=True,
)
@argument("batch", type=BATCH)
@wrap_async()
async def bake(
    root: Root,
    batch: str,
    local_executor: bool,
    meta_from_file: Optional[str],
    param: List[Tuple[str, str]],
    name: Optional[str],
    tag: Sequence[str],
) -> None:
    """Start a batch.

    Run BATCH pipeline remotely on the cluster.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage, root)
        )
        params = {key: value for key, value in param}
        if meta_from_file is not None:
            bake_meta = parse_bake_meta(LocalPath(meta_from_file))
            params = {**bake_meta, **params}
        await runner.bake(
            batch_name=batch,
            local_executor=local_executor,
            params=params,
            name=name,
            tags=tag,
        )


@click.command(hidden=True)
@click.argument("bake_id")
@wrap_async()
async def execute(
    root: Root,
    bake_id: str,
) -> None:
    """Start a batch.

    Run BATCH pipeline remotely on the cluster.
    """
    # neuro-flow execute is run in linux container only,
    # Linux signals are always defined.
    for signame in (
        signal.SIGHUP,
        signal.SIGINT,
        signal.SIGQUIT,
        signal.SIGTSTP,
        signal.SIGTERM,
        signal.SIGTTIN,
        signal.SIGTTOU,
        signal.SIGWINCH,
    ):
        # ignore everything, use neuro-flow cancel to stop the master job.
        signal.signal(signame, signal.SIG_IGN)
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage, root)
        )
        await runner.process(bake_id)


@click.command()
@click.option(
    "-t",
    "--tag",
    metavar="TAG",
    type=str,
    help="Filter out bakes by tag (multiple option)",
    multiple=True,
)
@option(
    "--since",
    metavar="DATE_OR_TIMEDELTA",
    help="Show bakes created after a specific date (including). "
    "Use value of format '1d2h3m4s' to specify moment in "
    "past relatively to current time.",
)
@option(
    "--until",
    metavar="DATE_OR_TIMEDELTA",
    help="Show bakes created before a specific date (including). "
    "Use value of format '1d2h3m4s' to specify moment in "
    "past relatively to current time.",
)
@option(
    "--recent-first/--recent-last",
    is_flag=True,
    default=False,
    help="Show newer bakes first or last",
)
@wrap_async()
async def bakes(
    root: Root,
    tag: Sequence[str],
    since: Optional[str],
    until: Optional[str],
    recent_first: bool,
) -> None:
    """List existing bakes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage, root)
        )
        await runner.list_bakes(
            tags=set(tag),
            since=_parse_date(since),
            until=_parse_date(until),
            recent_first=recent_first,
        )


@click.command()
@argument("bake", type=BAKE)
@option(
    "-a",
    "--attempt",
    type=int,
    default=-1,
    help="Attempt number, the last attempt by default",
)
@click.option(
    "-o",
    "--output-graph",
    type=click.Path(file_okay=True, dir_okay=False, writable=True),
    help=(
        "A path to Graphviz (DOT) file. "
        "Autogenerated from BAKE_ID and attempt number by default"
    ),
)
@click.option(
    "--dot",
    is_flag=True,
    help=("Save DOT file with tasks statuses."),
)
@click.option(
    "--pdf",
    is_flag=True,
    help=("Save PDF file with tasks statuses."),
)
@click.option(
    "--view",
    is_flag=True,
    help=("Open generated PDF file with tasks statuses."),
)
@wrap_async()
async def inspect(
    root: Root,
    bake: str,
    attempt: int,
    output_graph: Optional[str],
    dot: bool,
    pdf: bool,
    view: bool,
) -> None:
    """Inspect a bake.

    Display a list of started/finished tasks of BAKE\\_ID.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage, root)
        )
        if output_graph is not None:
            real_output: Optional[LocalPath] = LocalPath(output_graph)
        else:
            real_output = None
        bake_id = await resolve_bake(bake, project=runner.project_id, storage=storage)

        await runner.inspect(
            bake_id,
            attempt_no=attempt,
            output=real_output,
            save_dot=dot,
            save_pdf=pdf,
            view_pdf=view,
        )


@click.command()
@argument("bake", type=BAKE)
@argument(
    "task_id",
    type=BakeTaskType(
        include_started=False,
        include_finished=True,
        bake_id_param_name="bake",
        attempt_no_param_name="attempt",
    ),
)
@click.option(
    "-a",
    "--attempt",
    type=int,
    default=-1,
    help="Attempt number, the last attempt by default",
)
@click.option(
    "-r/-R",
    "--raw/--no-raw",
    default=False,
    help=(
        "Raw mode disables the output postprocessing "
        "(the output is processed by default)"
    ),
)
@wrap_async()
async def show(
    root: Root,
    bake: str,
    attempt: int,
    task_id: str,
    raw: bool,
) -> None:
    """Show output of baked task.

    Display a logged output of TASK\\_ID from BAKE\\_ID.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage, root)
        )
        bake_id = await resolve_bake(bake, project=runner.project_id, storage=storage)
        await runner.logs(bake_id, task_id, attempt_no=attempt, raw=raw)


@click.command()
@argument("bake", type=BAKE)
@click.option(
    "-a",
    "--attempt",
    type=int,
    default=-1,
    help="Attempt number, the last attempt by default",
)
@wrap_async()
async def cancel(
    root: Root,
    bake: str,
    attempt: int,
) -> None:
    """Cancel a bake.

    Cancel a bake execution by stopping all started tasks.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage, root)
        )
        bake_id = await resolve_bake(bake, project=runner.project_id, storage=storage)
        await runner.cancel(bake_id, attempt_no=attempt)


@click.command()
@argument("batch", type=BATCH_OR_ALL)
@argument("task_id", type=str, required=False)
@wrap_async()
async def clear_cache(
    root: Root,
    batch: str,
    task_id: Optional[str],
) -> None:
    """Clear cache.

    Use `neuro-flow clear-cache <BATCH>` for cleaning up the cache for BATCH;
    Use `neuro-flow clear-cache <BATCH> <TASK_ID>` for cleaning up the cache
    for TASK_ID in BATCH;

    `neuro-flow clear-cache ALL` clears all caches.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage, root)
        )
        if batch == "ALL":
            await runner.clear_cache(None)
        else:
            await runner.clear_cache(batch, task_id)


@click.command()
@argument("bake", type=BAKE)
@option(
    "-a",
    "--attempt",
    type=int,
    default=-1,
    help="Attempt number, the last attempt by default",
)
@option("--local-executor", is_flag=True, default=False, help="Run primary job locally")
@option(
    "--from-failed/--no-from-failed",
    is_flag=True,
    default=True,
    help="Restart from the point of failure",
)
@wrap_async()
async def restart(
    root: Root,
    bake: str,
    attempt: int,
    from_failed: bool,
    local_executor: bool,
) -> None:
    """Start a batch.

    Run BATCH pipeline remotely on the cluster.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage, root)
        )
        bake_id = await resolve_bake(bake, project=runner.project_id, storage=storage)
        await runner.restart(
            bake_id,
            attempt_no=attempt,
            from_failed=from_failed,
            local_executor=local_executor,
        )


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if value:
        try:
            return isoparse(value)
        except ValueError:
            try:
                delta = parse_timedelta(value)
                return datetime.now(timezone.utc) - delta
            except click.UsageError:
                raise ValueError(
                    "Date should be either in ISO-8601 format or "
                    "relative delta of form 1d2h3m4s"
                )
    else:
        return None
