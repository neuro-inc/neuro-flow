import click
import functools
import inspect
import logging
import sys
from neuromation.api import get as api_get
from neuromation.cli.asyncio_utils import Runner
from typing import Any, Awaitable, Callable, Optional, TypeVar

from .batch_runner import BatchRunner
from .live_runner import LiveRunner
from .parser import ConfigDir, find_live_config, find_workspace, parse_live
from .storage import BatchFSStorage, BatchStorage


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack


_T = TypeVar("_T")


def wrap_async(callback: Callable[..., Awaitable[_T]],) -> Callable[..., _T]:
    assert inspect.iscoroutinefunction(callback)

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
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
        await runner.ps()


@main.command()
@click.argument("job-id")
@wrap_async
async def run(config_dir: ConfigDir, job_id: str) -> None:
    """Run a job.

    RUN job JOB-ID or ATTACH to it if the job is already running
    """
    config_path = find_live_config(config_dir)
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
        await runner.run(job_id)


@main.command()
@click.argument("job-id")
@wrap_async
async def logs(config_dir: ConfigDir, job_id: str) -> None:
    """Print logs.

    Displys logs for JOB-ID
    """
    config_path = find_live_config(config_dir)
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
        await runner.logs(job_id)


@main.command()
@click.argument("job-id")
@wrap_async
async def status(config_dir: ConfigDir, job_id: str) -> None:
    """Show job status.

    Print status for JOB-ID
    """
    config_path = find_live_config(config_dir)
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
        await runner.status(job_id)


@main.command()
@click.argument("job-id")
@wrap_async
async def kill(config_dir: ConfigDir, job_id: str) -> None:
    """Kill a job.

    Kill JOB-ID, use `kill ALL` for killing all jobs."""
    config_path = find_live_config(config_dir)
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
        if job_id != "ALL":
            await runner.kill(job_id)
        else:
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
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
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
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
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
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
        if volume != "ALL":
            await runner.clean(volume)
        else:
            await runner.clean_all()


@main.command()
@wrap_async
async def mkvolumes(config_dir: ConfigDir) -> None:
    """Create all remote folders for volumes."""
    config_path = find_live_config(config_dir)
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
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
    flow = parse_live(config_path.workspace, config_path.config_file)
    async with LiveRunner(flow) as runner:
        await runner.build(image)


# #### pipeline commands ####


@main.command()
@click.argument("batch")
@wrap_async
async def start(config_dir: ConfigDir, batch: str) -> None:
    """Start a pipeline.

    Run BATCH remotely on the cluster.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: BatchStorage = await stack.enter_async_context(BatchFSStorage(client))
        runner = await stack.enter_async_context(
            BatchRunner(config_dir, client, storage)
        )
        await runner.bake(batch)
