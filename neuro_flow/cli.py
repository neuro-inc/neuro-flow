import click
import functools
import logging
import sys
from inspect import iscoroutinefunction
from neuromation.api import get as api_get
from neuromation.cli.asyncio_utils import Runner
from typing import Any, Awaitable, Callable, Optional, Tuple, TypeVar

from .batch_runner import BatchRunner
from .live_runner import LiveRunner
from .parser import ConfigDir, find_live_config, find_workspace
from .storage import BatchFSStorage, BatchStorage


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack


_T = TypeVar("_T")


def wrap_async(
    callback: Callable[..., Awaitable[_T]],
) -> Callable[..., _T]:
    assert iscoroutinefunction(callback)

    # N.B. the decorator implies @click.pass_obj
    @click.pass_obj
    @functools.wraps(callback)
    def wrapper(*args: Any, **kwargs: Any) -> _T:
        with Runner() as runner:
            return runner.run(callback(*args, **kwargs))

    return wrapper


@click.group()
@click.option(
    "--config",
    type=click.Path(dir_okay=True, file_okay=False),
    required=False,
    help=(
        "Path to a directory with .neuro folder inside, "
        "automatic lookup is performed if not set (default)"
    ),
    default=None,
    metavar="PATH",
)
@click.pass_context
def main(ctx: click.Context, config: Optional[str]) -> None:
    logging.basicConfig(level=logging.INFO)
    config_dir = find_workspace(config)
    ctx.obj = config_dir


# #### job commands ####


@main.command()
@wrap_async
async def ps(config_dir: ConfigDir) -> None:
    """List all jobs"""
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        await runner.ps()


@main.command()
@click.option("-s", "--suffix", help="Optional suffix for multi-jobs")
@click.argument("job-id")
@click.argument("args", nargs=-1)
@wrap_async
async def run(
    config_dir: ConfigDir,
    job_id: str,
    suffix: Optional[str],
    args: Optional[Tuple[str]],
) -> None:
    """Run a job.

    RUN job JOB-ID or ATTACH to it if the job is already running

    For multi-jobs an explicit job suffix can be used with explicit job arguments.
    """
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        await runner.run(job_id, suffix, args)


@main.command()
@click.argument("job-id")
@click.argument("suffix", required=False)
@wrap_async
async def logs(config_dir: ConfigDir, job_id: str, suffix: Optional[str]) -> None:
    """Print logs.

    Display logs for JOB-ID
    """
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        await runner.logs(job_id, suffix)


@main.command()
@click.argument("job-id")
@click.argument("suffix", required=False)
@wrap_async
async def status(config_dir: ConfigDir, job_id: str, suffix: Optional[str]) -> None:
    """Show job status.

    Print status for JOB-ID
    """
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        await runner.status(job_id, suffix)


@main.command()
@click.argument("job-id")
@click.argument("suffix", required=False)
@wrap_async
async def kill(config_dir: ConfigDir, job_id: str, suffix: Optional[str]) -> None:
    """Kill a job.

    Kill JOB-ID, use `kill ALL` for killing all jobs."""
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        if job_id != "ALL":
            await runner.kill(job_id, suffix)
        else:
            if suffix is not None:
                raise click.BadArgumentUsage(
                    "Suffix is not supported when killing ALL jobs"
                )
            await runner.kill_all()


# #### storage commands ####


@main.command()
@click.argument("volume")
@wrap_async
async def upload(config_dir: ConfigDir, volume: str) -> None:
    """Upload volume.

    Upload local files to remote for VOLUME,
    use `upload ALL` for uploading all volumes."""
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        if volume != "ALL":
            await runner.upload(volume)
        else:
            await runner.upload_all()


@main.command()
@click.argument("volume")
@wrap_async
async def download(config_dir: ConfigDir, volume: str) -> None:
    """Download volume.

    Download remote files to local for VOLUME,
    use `download ALL` for downloading all volumes."""
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        if volume != "ALL":
            await runner.download(volume)
        else:
            await runner.download_all()


@main.command()
@click.argument("volume")
@wrap_async
async def clean(config_dir: ConfigDir, volume: str) -> None:
    """Clean volume.

    Clean remote files on VOLUME,
    use `clean ALL` for cleaning up all volumes."""
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        if volume != "ALL":
            await runner.clean(volume)
        else:
            await runner.clean_all()


@main.command()
@wrap_async
async def mkvolumes(config_dir: ConfigDir) -> None:
    """Create all remote folders for volumes."""
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        await runner.mkvolumes()


# #### image commands ####


@main.command()
@click.argument("image")
@wrap_async
async def build(config_dir: ConfigDir, image: str) -> None:
    """Build an image.

    Assemble the IMAGE remotely and publish it.
    """
    config_path = find_live_config(config_dir)
    async with LiveRunner(config_path.workspace, config_path.config_file) as runner:
        if image == "ALL":
            await runner.build_all()
        else:
            await runner.build(image)


# #### pipeline commands ####


@main.command()
@click.argument("batch")
@wrap_async
async def bake(config_dir: ConfigDir, batch: str) -> None:
    """Start a batch.

    Run BATCH pipeline remotely on the cluster.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        await runner.bake(batch)


@main.command()
@wrap_async
async def bakes(config_dir: ConfigDir) -> None:
    """List existing bakes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        await runner.list_bakes()


@main.command()
@click.argument("bake_id")
@click.option(
    "-a",
    "--attempt",
    type=int,
    default=-1,
    help="Attempt number, the last attempt by default",
)
@wrap_async
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


@main.command()
@click.argument("bake_id")
@click.argument("task_id")
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
@wrap_async
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
