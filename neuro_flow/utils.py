import click
from neuromation.api import JobStatus
from typing import Union

from .types import FullID, TaskStatus


COLORS = {
    TaskStatus.PENDING: "cyan",
    TaskStatus.RUNNING: "blue",
    TaskStatus.SUCCEEDED: "green",
    TaskStatus.CANCELLED: "yellow",
    TaskStatus.SKIPPED: "magenta",
    TaskStatus.FAILED: "red",
    TaskStatus.UNKNOWN: "bright_black",
}


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

TERMINATED_JOB_STATUSES = {
    JobStatus.FAILED,
    JobStatus.SUCCEEDED,
    JobStatus.CANCELLED,
}


JOB_TAG_PATTERN = r"\A[a-z](?:[-.:/]?[a-z0-9]){0,255}\Z"
