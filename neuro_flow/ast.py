# Dataclasses
import enum
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import AbstractSet, List, Mapping, Optional, Sequence

from neuromation.api import HTTPPort
from yarl import URL


# There are 'batch' for pipelined mode and 'job' for interactive one
# (while 'batches' are technically just non-interactive jobs.


class Kind(enum.Enum):
    JOB = "job"  # interactive mode.
    BATCH = "batch"  # pipelined mode


@dataclass(frozen=True)
class Volume:
    id: str  # explicitly set or defived from url/path pair.
    uri: URL  # storage URI
    mount: PurePosixPath  # mount path inside container
    ro: bool  # True if mounted in read-only mode, False for read-write


@dataclass(frozen=True)
class Image:
    id: str
    uri: URL
    context: Path
    dockerfile: Path
    build_args: Mapping[str, str]


@dataclass(frozen=True)
class ExecUnit:
    name: str
    image: str  # ImageRef
    preset: Optional[str]
    http: Optional[HTTPPort]
    entrypoint: Optional[str]
    cmd: str
    workdir: Optional[PurePosixPath]
    env: Mapping[str, str]
    volumes: Sequence[str]  # Sequence[VolumeRef]
    tags: AbstractSet[str]
    life_span: Optional[float]


@dataclass(frozen=True)
class Job(ExecUnit):
    # Interactive job used by Kind.Live flow
    id: str
    title: Optional[str]  # Autocalculated if not passed explicitly

    detach: bool
    browse: bool


@dataclass(frozen=True)
class Step(ExecUnit):
    # A step of a batch
    id: str
    title: Optional[str]  # Autocalculated if not passed explicitly

    image: str  # ImageRef
    preset: Optional[str]
    http: Optional[HTTPPort]

    entrypoint: Optional[str]
    cmd: str

    volumes: Sequence[str]  # Sequence[VolumeRef]
    tags: AbstractSet[str]

    env: Mapping[str, str]
    working_directory: Optional[str]

    life_span: Optional[float]
    continue_on_error: bool
    # if: str -- skip conditionally


@dataclass(frozen=True)
class Batch:
    # A set of steps, used in non-interactive mode
    # All steps share the same implicit persistent disk volume

    id: str
    title: Optional[str]  # Autocalculated if not passed explicitly
    needs: List[str]  # BatchRef
    steps: List[Step]

    # matrix? Do we need a build matrix? Yes probably.

    # outputs: Mapping[str, str] -- metadata for communicating between batches.
    # will be added later

    # defaults for steps
    name: str
    image: Optional[str]  # ImageRef
    preset: Optional[str]

    volumes: Sequence[str]  # Sequence[VolumeRef]
    tags: AbstractSet[str]

    env: Mapping[str, str]
    workdir: Optional[PurePosixPath]

    life_span: Optional[float]
    continue_on_error: bool
    # if: str -- skip conditionally


@dataclass(frozen=True)
class BaseFlow:
    kind: Kind
    title: Optional[str]  # explicitly set or defived from config file name.

    # cluster: str  # really need it?

    images: Sequence[Image]
    volumes: Sequence[Volume]

    tags: AbstractSet[str]

    env: Mapping[str, str]
    workdir: Optional[str]

    life_span: Optional[float]


@dataclass(frozen=True)
class InteractiveFlow(BaseFlow):
    # self.kind == Kind.Job
    jobs: Mapping[str, Job]


@dataclass(frozen=True)
class BatchFlow(BaseFlow):
    # self.kind == Kind.Batch
    batches: Mapping[str, Batch]
