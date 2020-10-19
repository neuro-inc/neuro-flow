import asyncio
import click
from neuromation.api import JobStatus
from typing import Union

from .types import COLORS, FullID, TaskStatus


def fmt_status(status: Union[JobStatus, TaskStatus]) -> str:
    if isinstance(status, JobStatus):
        status = TaskStatus(status)
    else:
        assert isinstance(status, TaskStatus)
    return click.style(status.value, fg=COLORS.get(status, "reset"))


def fmt_id(id: Union[str, FullID]) -> str:
    if isinstance(id, str):
        s_id = id
    else:
        s_id = ".".join(id)
    return click.style(s_id, bold=True)


def fmt_raw_id(raw_id: str) -> str:
    return click.style(raw_id, dim=True)


RUNNING_JOB_STATUSES = {JobStatus.PENDING, JobStatus.RUNNING}
RUNNING_TASK_STATUSES = {TaskStatus.PENDING, TaskStatus.RUNNING}

TERMINATED_JOB_STATUSES = {
    JobStatus.FAILED,
    JobStatus.SUCCEEDED,
    JobStatus.CANCELLED,
}

TERMINATED_TASK_STATUSES = {
    TaskStatus.FAILED,
    TaskStatus.SUCCEEDED,
    TaskStatus.CANCELLED,
}


JOB_TAG_PATTERN = r"\A[a-z](?:[-.:/]?[a-z0-9]){0,255}\Z"


async def run_subproc(exe: str, *args: str) -> None:
    proc = await asyncio.create_subprocess_exec(exe, *args)
    try:
        retcode = await proc.wait()
        if retcode:
            raise SystemExit(retcode)
    finally:
        if proc.returncode is None:
            # Kill neuro process if not finished
            # (e.g. if KeyboardInterrupt or cancellation was received)
            proc.kill()
            await proc.wait()
