import click
import sys
from neuromation.api import get as api_get
from typing import Optional

from neuro_flow.batch_executor import ExecutorData
from neuro_flow.batch_runner import BatchRunner
from neuro_flow.cli.click_types import BAKE, BATCH, FINISHED_TASK_AFTER_BAKE
from neuro_flow.cli.utils import argument, option, wrap_async
from neuro_flow.parser import ConfigDir
from neuro_flow.storage import BatchFSStorage, BatchStorage
from neuro_flow.types import LocalPath


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack


@click.command()
@option("--local-executor", is_flag=True, default=False, help="Run primary job locally")
@argument("batch", type=BATCH)
@wrap_async()
async def bake(config_dir: ConfigDir, batch: str, local_executor: bool) -> None:
    """Start a batch.

    Run BATCH pipeline remotely on the cluster.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        await runner.bake(batch, local_executor)


@click.command(hidden=True)
@click.argument("executor_data")
@wrap_async()
async def execute(config_dir: ConfigDir, executor_data: str) -> None:
    """Start a batch.

    Run BATCH pipeline remotely on the cluster.
    """
    async with AsyncExitStack() as stack:
        data = ExecutorData.parse(executor_data)
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        await runner.process(data)


@click.command()
@wrap_async()
async def bakes(config_dir: ConfigDir) -> None:
    """List existing bakes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
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
@wrap_async()
async def inspect(config_dir: ConfigDir, bake_id: str, attempt: int) -> None:
    """Inspect a bake.

    Display a list of started/finished tasks of BAKE_ID.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        await runner.inspect(bake_id, attempt_no=attempt)


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
    config_dir: ConfigDir, bake_id: str, attempt: int, task_id: str, raw: bool
) -> None:
    """Show output of baked task.

    Display a logged output of TASK_ID from BAKE_ID.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
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
async def cancel(config_dir: ConfigDir, bake_id: str, attempt: int) -> None:
    """Cancel a bake.

    Cancel a bake execution by stopping all started tasks.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        await runner.cancel(bake_id, attempt_no=attempt)


@click.command()
@argument("batch", type=BATCH)
@wrap_async()
async def clear_cache(config_dir: ConfigDir, batch: str) -> None:
    """Clear cache.

    Use `neuro-flow clear-cache <BATCH>` for cleaning up the cache for BATCH;

    `neuro-flow clear-cache ALL` clears all caches.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        if batch == "ALL":
            await runner.clear_cache(None)
        else:
            await runner.clear_cache(batch)


@click.command()
@argument("batch", type=BATCH)
@click.option(
    "-o",
    "--output",
    type=click.Path(file_okay=True, dir_okay=False, writable=True),
    help="A path to with Graphviz (DOT) file.",
)
@wrap_async()
async def graph(config_dir: ConfigDir, batch: str, output: Optional[str]) -> None:
    """Build.

    Use `neuro-flow clear-cache <BATCH>` for cleaning up the cache for BATCH;

    `neuro-flow clear-cache ALL` clears all caches.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        if output is not None:
            real_output: Optional[LocalPath] = LocalPath(output)
        else:
            real_output = None
        await runner.graph(batch, real_output)
