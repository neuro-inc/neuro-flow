import click
import functools
import inspect
from neuromation.cli.asyncio_utils import Runner
from typing import Any, Awaitable, Callable, Optional, TypeVar

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

    Kill JOB-ID, use `kill ALL` for killing all jobs."""
    async with InteractiveRunner(flow) as runner:
        if job_id != "ALL":
            await runner.kill(job_id)
        else:
            await runner.kill_all()


# #### storage commands ####


@main.command()
@click.argument("volume")
@wrap_async
async def upload(flow: ast.InteractiveFlow, volume: str) -> None:
    """Upload volume.

    Upload local files to remote for VOLUME,
    use `upload ALL` for uploading all volumes."""
    async with InteractiveRunner(flow) as runner:
        if volume != "ALL":
            await runner.upload(volume)
        else:
            await runner.upload_all()


@main.command()
@click.argument("volume")
@wrap_async
async def download(flow: ast.InteractiveFlow, volume: str) -> None:
    """Download volume.

    Download remote files to local for VOLUME,
    use `download ALL` for downloading all volumes."""
    async with InteractiveRunner(flow) as runner:
        if volume != "ALL":
            await runner.download(volume)
        else:
            await runner.download_all()


@main.command()
@click.argument("volume")
@wrap_async
async def clean(flow: ast.InteractiveFlow, volume: str) -> None:
    """Clean volume.

    Clean remote files on VOLUME,
    use `clean ALL` for cleaning up all volumes."""
    async with InteractiveRunner(flow) as runner:
        if volume != "ALL":
            await runner.clean(volume)
        else:
            await runner.clean_all()


@main.command()
@wrap_async
async def mkvolumes(flow: ast.InteractiveFlow) -> None:
    """Create all remote folders for volumes."""
    async with InteractiveRunner(flow) as runner:
        await runner.mkvolumes()


# #### image commands ####


@main.command()
@click.argument("image")
@wrap_async
async def build(flow: ast.InteractiveFlow, image: str) -> None:
    """Build an image.

    Assemble the IMAGE remotely and publish it.
    """
    async with InteractiveRunner(flow) as runner:
        await runner.build(image)
