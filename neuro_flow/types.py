import enum
from pathlib import Path, PurePosixPath
from typing import Tuple


LocalPath = Path
RemotePath = PurePosixPath
FullID = Tuple[str, ...]


class TaskStatus(str, enum.Enum):
    # Almost copy of neuromation.api.JobStatus, but adds new SKIPPED state

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    DISABLED = "disabled"
