from dataclasses import dataclass

import enum
from pathlib import Path, PurePosixPath
from typing import ClassVar, List, Sequence, Tuple


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
    # Almost copy of apolo_sdk.JobStatus, but adds new SKIPPED state

    def __rich__(self) -> str:
        return f"[{COLORS[self]}]{self.value}"

    UNKNOWN = "unknown"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    CACHED = "cached"

    @property
    def is_pending(self) -> bool:
        return self == self.PENDING

    @property
    def is_running(self) -> bool:
        return self == self.RUNNING

    @property
    def is_finished(self) -> bool:
        return self in (
            self.SUCCEEDED,
            self.FAILED,
            self.CANCELLED,
            self.SKIPPED,
            self.CACHED,
        )

    @classmethod
    def values(cls) -> List[str]:
        return [item.value for item in cls]

    @classmethod
    def active_values(cls) -> List[str]:
        return [item.value for item in cls if not item.is_finished]

    @classmethod
    def finished_values(cls) -> List[str]:
        return [item.value for item in cls if item.is_finished]


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


class ImageStatus(str, enum.Enum):
    PENDING = "pending"
    BUILDING = "building"
    BUILT = "built"
    BUILD_FAILED = "build_failed"
    CACHED = "cached"

    def __rich__(self) -> str:
        return f"[{IMAGE_STATUS_COLORS[self]}]{self.value}"


IMAGE_STATUS_COLORS = {
    ImageStatus.PENDING: "cyan",
    ImageStatus.BUILDING: "blue",
    ImageStatus.BUILT: "green",
    ImageStatus.BUILD_FAILED: "red",
    ImageStatus.CACHED: "magenta",
}


@dataclass(frozen=True)
class GitInfo:
    sha: str
    branch: str
    tags: Sequence[str]
