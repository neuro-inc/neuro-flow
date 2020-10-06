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
            cls.instance = super(AlwaysT, cls).__new__(cls)
        return cls.instance


class TaskStatus(str, enum.Enum):
    # Almost copy of neuromation.api.JobStatus, but adds new SKIPPED state

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"
