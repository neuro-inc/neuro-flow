import enum
from pathlib import Path, PurePosixPath
from typing import ClassVar, Tuple


LocalPath = Path
RemotePath = PurePosixPath
FullID = Tuple[str, ...]


class AlwaysT:
    instance: ClassVar["AlwaysT"]

    def __str__(self) -> str:
        return "always()"

    def __new__(cls) -> "AlwaysT":
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance


class TaskStatus(str, enum.Enum):
    # Almost copy of neuro_sdk.JobStatus, but adds new SKIPPED state

    def __rich__(self) -> str:
        return f"[{COLORS[self]}]{self}"

    UNKNOWN = "unknown"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    CACHED = "cached"


COLORS = {
    TaskStatus.UNKNOWN: "reverse bright_black",
    TaskStatus.PENDING: "cyan",
    TaskStatus.RUNNING: "blue",
    TaskStatus.SUCCEEDED: "green",
    TaskStatus.FAILED: "red",
    TaskStatus.CANCELLED: "yellow",
    TaskStatus.SKIPPED: "bright_black",
    TaskStatus.CACHED: "magenta",
}
