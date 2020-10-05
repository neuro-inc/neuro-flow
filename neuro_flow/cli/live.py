import click
from typing import Optional, Tuple

from neuro_flow.cli.click_types import LIVE_JOB, LIVE_JOB_OR_ALL, SUFFIX_AFTER_LIVE_JOB
from neuro_flow.cli.utils import argument, option, wrap_async
from neuro_flow.live_runner import LiveRunner
from neuro_flow.parser import ConfigDir


@click.command()
@wrap_async()
async def ps(config_dir: ConfigDir) -> None:
    """List all jobs"""
    async with LiveRunner(config_dir) as runner:
        await runner.ps()


@click.command()
@option("-s", "--suffix", help="Optional suffix for multi-jobs")
@argument("job-id", type=LIVE_JOB)
@argument("args", nargs=-1)
@wrap_async()
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
    async with LiveRunner(config_dir) as runner:
        await runner.run(job_id, suffix, args)


@click.command()
@argument("job-id", type=LIVE_JOB)
@argument("suffix", required=False, type=SUFFIX_AFTER_LIVE_JOB)
@wrap_async()
async def logs(config_dir: ConfigDir, job_id: str, suffix: Optional[str]) -> None:
    """Print logs.

    Display logs for JOB-ID
    """
    async with LiveRunner(config_dir) as runner:
        await runner.logs(job_id, suffix)


@click.command()
@argument("job-id", type=LIVE_JOB)
@argument("suffix", required=False, type=SUFFIX_AFTER_LIVE_JOB)
@wrap_async()
async def status(config_dir: ConfigDir, job_id: str, suffix: Optional[str]) -> None:
    """Show job status.

    Print status for JOB-ID
    """
    async with LiveRunner(config_dir) as runner:
        await runner.status(job_id, suffix)


@click.command()
@argument("job-id", type=LIVE_JOB_OR_ALL)
@argument("suffix", required=False, type=SUFFIX_AFTER_LIVE_JOB)
@wrap_async()
async def kill(config_dir: ConfigDir, job_id: str, suffix: Optional[str]) -> None:
    """Kill a job.

    Kill JOB-ID, use `kill ALL` for killing all jobs."""
    async with LiveRunner(config_dir) as runner:
        if job_id != "ALL":
            await runner.kill(job_id, suffix)
        else:
            if suffix is not None:
                raise click.BadArgumentUsage(
                    "Suffix is not supported when killing ALL jobs"
                )
            await runner.kill_all()
