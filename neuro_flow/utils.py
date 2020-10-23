import asyncio
import datetime
import humanize
from neuromation.api import JobStatus
from typing import Optional, Union, cast

from .types import COLORS, FullID, TaskStatus


def fmt_status(status: Union[JobStatus, TaskStatus]) -> str:
    if isinstance(status, JobStatus):
        status = TaskStatus(status)
    else:
        assert isinstance(status, TaskStatus)
    color = COLORS.get(status, "none")
    return f"[{color}]{status.value}[/{color}]"


def fmt_id(id: Union[str, FullID]) -> str:
    if isinstance(id, str):
        s_id = id
    else:
        s_id = ".".join(id)
    return f"[b]{s_id}[/b]"


def fmt_raw_id(raw_id: str) -> str:
    return f"[bright_black]{raw_id}[/bright_black]"


def fmt_datetime(when: Optional[datetime.datetime]) -> str:
    if when is None:
        return "N/A"
    delta = datetime.datetime.now(datetime.timezone.utc) - when
    if delta < datetime.timedelta(days=1):
        return cast(str, humanize.naturaltime(delta))
    else:
        return cast(str, humanize.naturaldate(when.astimezone()))


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
