import functools
import inspect
from typing import Any, Awaitable, Callable, Optional, TypeVar

import click
from neuromation.cli.asyncio_utils import Runner

from . import ast
from .parser import find_interactive_config, parse_interactive
from .runner import InteractiveRunner


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
    type=click.Path(dir_okay=True, file_okay=True),
    required=False,
    help="Path to config file or directory with .neuro folder inside.",
    default=None,
    metavar="PATH",
)
@click.pass_context
def main(ctx: click.Context, config: Optional[str]) -> None:
    config_path = find_interactive_config(config)
    flow = parse_interactive(config_path.workspace, config_path.config_file)
    ctx.obj = flow


# #### job commands ####


@main.command()
@wrap_async
async def ps(flow: ast.InteractiveFlow) -> None:
    """List all jobs"""
    async with InteractiveRunner(flow) as runner:
        await runner.ps()


@main.command()
@click.argument("job-id")
@wrap_async
async def run(flow: ast.InteractiveFlow, job_id: str) -> None:
    """Run a job.

    RUN job JOB-ID or ATTACH to it if the job is already running
    """
    async with InteractiveRunner(flow) as runner:
        await runner.run(job_id)


@main.command()
@click.argument("job-id")
@wrap_async
async def logs(flow: ast.InteractiveFlow, job_id: str) -> None:
    """Print logs.

    Displys logs for JOB-ID
    """
    async with InteractiveRunner(flow) as runner:
        await runner.logs(job_id)


@main.command()
@click.argument("job-id")
@wrap_async
async def status(flow: ast.InteractiveFlow, job_id: str) -> None:
    """Show job status.

    Print status for JOB-ID
    """
    async with InteractiveRunner(flow) as runner:
        await runner.status(job_id)


@main.command()
@click.argument("job-id")
@wrap_async
async def kill(flow: ast.InteractiveFlow, job_id: str) -> None:
    """Kill a job.

    Kill JOB-ID"""
    async with InteractiveRunner(flow) as runner:
        await runner.kill(job_id)


@main.command()
@wrap_async
async def kill_all(flow: ast.InteractiveFlow) -> None:
    """Kill all jobs."""
    async with InteractiveRunner(flow) as runner:
        await runner.kill_all()


# #### storage commands ####


@main.command()
@click.argument("volume")
@wrap_async
async def upload(flow: ast.InteractiveFlow, volume: str) -> None:
    """Upload volume.

    Upload local files to remote for VOLUME"""
    async with InteractiveRunner(flow) as runner:
        await runner.upload(volume)


@main.command()
@click.argument("volume")
@wrap_async
async def download(flow: ast.InteractiveFlow, volume: str) -> None:
    """Download volume.

    Download remote files to local for VOLUME"""
    async with InteractiveRunner(flow) as runner:
        await runner.download(volume)


@main.command()
@click.argument("volume")
@wrap_async
async def clean(flow: ast.InteractiveFlow, volume: str) -> None:
    """Clean volume.

    Clean remote files on VOLUME"""
    async with InteractiveRunner(flow) as runner:
        await runner.clean(volume)


@main.command()
@wrap_async
async def upload_all(flow: ast.InteractiveFlow) -> None:
    """Upload all volumes."""
    async with InteractiveRunner(flow) as runner:
        await runner.upload_all()


@main.command()
@wrap_async
async def download_all(flow: ast.InteractiveFlow) -> None:
    """Download all volumes."""
    async with InteractiveRunner(flow) as runner:
        await runner.download_all()


@main.command()
@wrap_async
async def clean_all(flow: ast.InteractiveFlow) -> None:
    """Clean all volumes."""
    async with InteractiveRunner(flow) as runner:
        await runner.clean_all()


@main.command()
@wrap_async
async def mkvolumes(flow: ast.InteractiveFlow) -> None:
    """Create all remote folders for volumes."""
    async with InteractiveRunner(flow) as runner:
        await runner.mkvolumes()
