import click
import neuro_sdk
import sys
from typing import List, Optional, Sequence, Tuple

from neuro_flow.cli.click_types import (
    LIVE_JOB,
    LIVE_JOB_OR_ALL,
    PROJECT,
    LiveJobSuffixType,
)
from neuro_flow.cli.utils import argument, option, wrap_async
from neuro_flow.live_runner import LiveRunner

from ..storage.api import ApiStorage
from ..storage.base import Storage
from .root import Root


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack


@click.command()
@wrap_async()
async def ps(
    root: Root,
) -> None:
    """List all jobs"""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        await runner.ps()


@click.command()
@option("-s", "--suffix", help="Optional suffix for multi-jobs")
@option(
    "-p",
    "--param",
    type=(str, str),
    multiple=True,
    help="Set params of the batch config",
)
@option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print run command instead of starting job.",
)
@argument("job-id", type=LIVE_JOB)
@argument("args", nargs=-1)
@wrap_async()
async def run(
    root: Root,
    job_id: str,
    suffix: Optional[str],
    dry_run: bool,
    args: Optional[Tuple[str]],
    param: List[Tuple[str, str]],
) -> None:
    """Run a job.

    RUN job JOB-ID or ATTACH to it if the job is already running

    For multi-jobs an explicit job suffix can be used with explicit job arguments.
    """
    if args:
        root.console.print(
            "[yellow]args are deprecated, use --param instead",
        )
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        await runner.run(
            job_id,
            suffix=suffix,
            args=args,
            params={key: value for key, value in param},
            dry_run=dry_run,
        )


@click.command()
@argument("job-id", type=LIVE_JOB)
@argument("suffix", required=False, type=LiveJobSuffixType(job_id_param_name="job_id"))
@wrap_async()
async def logs(
    root: Root,
    job_id: str,
    suffix: Optional[str],
) -> None:
    """Print logs.

    Display logs for JOB-ID
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        await runner.logs(job_id, suffix)


@click.command()
@argument("job-id", type=LIVE_JOB)
@argument("suffix", required=False, type=LiveJobSuffixType(job_id_param_name="job_id"))
@wrap_async()
async def status(
    root: Root,
    job_id: str,
    suffix: Optional[str],
) -> None:
    """Show job status.

    Print status for JOB-ID
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        await runner.status(job_id, suffix)


@click.command()
@argument("job-id", type=LIVE_JOB_OR_ALL)
@argument("suffix", required=False, type=LiveJobSuffixType(job_id_param_name="job_id"))
@wrap_async()
async def kill(
    root: Root,
    job_id: str,
    suffix: Optional[str],
) -> None:
    """Kill a job.

    Kill JOB-ID, use `kill ALL` for killing all jobs."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        if job_id != "ALL":
            await runner.kill(job_id, suffix)
        else:
            if suffix is not None:
                raise click.BadArgumentUsage(
                    "Suffix is not supported when killing ALL jobs"
                )
            await runner.kill_all()


@click.command()
@argument("project_ids", type=PROJECT, nargs=-1, required=True)
@wrap_async()
async def delete_project(
    root: Root,
    project_ids: Sequence[str],
) -> None:
    """Completely remove project with all related entities"""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        for project_id in project_ids:
            await storage.project(yaml_id=project_id).delete()
            if root.verbosity >= 0:
                root.console.print(f"Project '{project_id}' was successfully removed.")
