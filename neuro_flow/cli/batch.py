import click
import neuro_sdk
import signal
import sys
from typing import List, Optional, Tuple

from neuro_flow.batch_executor import ExecutorData
from neuro_flow.batch_runner import BatchRunner
from neuro_flow.cli.click_types import (
    BAKE,
    BATCH,
    BATCH_OR_ALL,
    FINISHED_TASK_AFTER_BAKE,
)
from neuro_flow.cli.utils import argument, option, wrap_async
from neuro_flow.storage import APIStorage, NeuroStorageFS, Storage
from neuro_flow.types import LocalPath

from ..parser import parse_bake_meta
from .root import Root


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack


@click.command()
@option("--local-executor", is_flag=True, default=False, help="Run primary job locally")
@click.option(
    "--param", type=(str, str), multiple=True, help="Set params of the batch config"
)
@click.option(
    "--meta-from-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    help="File with params for batch.",
)
@argument("batch", type=BATCH)
@wrap_async()
async def bake(
    root: Root,
    batch: str,
    local_executor: bool,
    meta_from_file: Optional[str],
    param: List[Tuple[str, str]],
) -> None:
    """Start a batch.

    Run BATCH pipeline remotely on the cluster.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage)
        )
        params = {key: value for key, value in param}
        if meta_from_file is not None:
            bake_meta = parse_bake_meta(LocalPath(meta_from_file))
            params = {**bake_meta, **params}
        await runner.bake(batch, local_executor, params)


@click.command(hidden=True)
@click.argument("executor_data")
@wrap_async()
async def execute(
    root: Root,
    executor_data: str,
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
        data = ExecutorData.parse(executor_data)
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage)
        )
        await runner.process(data)


@click.command()
@wrap_async()
async def bakes(
    root: Root,
) -> None:
    """List existing bakes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage)
        )
        await runner.list_bakes()


@click.command()
@argument("bake_id", type=BAKE)
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
    bake_id: str,
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
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage)
        )
        if output_graph is not None:
            real_output: Optional[LocalPath] = LocalPath(output_graph)
        else:
            real_output = None
        await runner.inspect(
            bake_id,
            attempt_no=attempt,
            output=real_output,
            save_dot=dot,
            save_pdf=pdf,
            view_pdf=view,
        )


@click.command()
@argument("bake_id", type=BAKE)
@argument("task_id", type=FINISHED_TASK_AFTER_BAKE)
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
    bake_id: str,
    attempt: int,
    task_id: str,
    raw: bool,
) -> None:
    """Show output of baked task.

    Display a logged output of TASK\\_ID from BAKE\\_ID.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage)
        )
        await runner.logs(bake_id, task_id, attempt_no=attempt, raw=raw)


@click.command()
@argument("bake_id", type=BAKE)
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
    bake_id: str,
    attempt: int,
) -> None:
    """Cancel a bake.

    Cancel a bake execution by stopping all started tasks.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage)
        )
        await runner.cancel(bake_id, attempt_no=attempt)


@click.command()
@argument("batch", type=BATCH_OR_ALL)
@wrap_async()
async def clear_cache(
    root: Root,
    batch: str,
) -> None:
    """Clear cache.

    Use `neuro-flow clear-cache <BATCH>` for cleaning up the cache for BATCH;

    `neuro-flow clear-cache ALL` clears all caches.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage)
        )
        if batch == "ALL":
            await runner.clear_cache(None)
        else:
            await runner.clear_cache(batch)


@click.command()
@argument("bake_id", type=BAKE)
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
    bake_id: str,
    attempt: int,
    from_failed: bool,
    local_executor: bool,
) -> None:
    """Start a batch.

    Run BATCH pipeline remotely on the cluster.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            BatchRunner(root.config_dir, root.console, client, storage)
        )
        await runner.restart(
            bake_id,
            attempt_no=attempt,
            from_failed=from_failed,
            local_executor=local_executor,
        )
