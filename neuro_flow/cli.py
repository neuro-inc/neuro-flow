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
    flow = parse_interactive(config_path)
    ctx.obj = flow


@main.command()
@wrap_async
async def ps(flow: ast.InteractiveFlow) -> None:
    async with InteractiveRunner(flow) as runner:
        await runner.ps()


@main.command()
@click.argument("job-id")
@wrap_async
async def run(flow: ast.InteractiveFlow, job_id: str) -> None:
    async with InteractiveRunner(flow) as runner:
        await runner.run(job_id)


@main.command()
@click.argument("job-id")
@wrap_async
async def logs(flow: ast.InteractiveFlow, job_id: str) -> None:
    async with InteractiveRunner(flow) as runner:
        await runner.logs(job_id)


@main.command()
@click.argument("job-id")
@wrap_async
async def kill(flow: ast.InteractiveFlow, job_id: str) -> None:
    async with InteractiveRunner(flow) as runner:
        await runner.kill(job_id)


@main.command()
@wrap_async
async def kill_all(flow: ast.InteractiveFlow) -> None:
    async with InteractiveRunner(flow) as runner:
        await runner.kill_all()
