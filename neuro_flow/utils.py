import click
from neuromation.api import JobStatus
from typing import Union

from .types import FullID


COLORS = {
    JobStatus.PENDING: "cyan",
    JobStatus.RUNNING: "blue",
    JobStatus.SUCCEEDED: "green",
    JobStatus.CANCELLED: "yellow",
    JobStatus.FAILED: "red",
    JobStatus.UNKNOWN: "bright_black",
}


def fmt_status(status: JobStatus) -> str:
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
