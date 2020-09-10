import click
from neuromation.api import JobStatus


COLORS = {
    JobStatus.PENDING: "yellow",
    JobStatus.RUNNING: "blue",
    JobStatus.SUCCEEDED: "green",
    JobStatus.CANCELLED: "green",
    JobStatus.FAILED: "red",
    JobStatus.UNKNOWN: "yellow",
}


def format_job_status(status: JobStatus) -> str:
    return click.style(status.value, fg=COLORS.get(status, "reset"))


RUNNING_JOB_STATUSES = {JobStatus.PENDING, JobStatus.RUNNING}

TERMINATED_JOB_STATUSES = {
    JobStatus.FAILED,
    JobStatus.SUCCEEDED,
    JobStatus.CANCELLED,
}


JOB_TAG_PATTERN = r"\A[a-z](?:[-.:/]?[a-z0-9]){0,255}\Z"
