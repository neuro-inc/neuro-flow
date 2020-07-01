# Dataclasses
import enum
from dataclasses import dataclass
from typing import AbstractSet, List, Mapping, Optional, Sequence

from neuromation.api import HTTPPort

from .expr import (
    BoolExpr,
    LocalPathExpr,
    OptFloatExpr,
    OptRemotePathExpr,
    OptStrExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)


# There are 'batch' for pipelined mode and 'job' for interactive one
# (while 'batches' are technically just non-interactive jobs.


class Kind(enum.Enum):
    JOB = "job"  # interactive mode.
    BATCH = "batch"  # pipelined mode


@dataclass(frozen=True)
class Volume:
    id: str  # explicitly set or defived from url/path pair.
    uri: URIExpr  # storage URI
    mount: RemotePathExpr  # mount path inside container
    ro: BoolExpr  # True if mounted in read-only mode, False for read-write


@dataclass(frozen=True)
class Image:
    id: str
    uri: URIExpr
    context: LocalPathExpr
    dockerfile: LocalPathExpr
    build_args: Mapping[str, StrExpr]


@dataclass(frozen=True)
class ExecUnit:
    name: StrExpr
    image: StrExpr
    preset: OptStrExpr
    http: Optional[HTTPPort]
    entrypoint: OptStrExpr
    cmd: StrExpr
    workdir: OptRemotePathExpr
    env: Mapping[str, StrExpr]
    volumes: Sequence[StrExpr]  # Sequence[VolumeRef]
    tags: AbstractSet[StrExpr]
    life_span: OptFloatExpr


@dataclass(frozen=True)
class Job(ExecUnit):
    # Interactive job used by Kind.Live flow
    id: str
    title: OptStrExpr  # Autocalculated if not passed explicitly

    detach: BoolExpr
    browse: BoolExpr


@dataclass(frozen=True)
class Step(ExecUnit):
    # A step of a batch
    id: str
    title: OptStrExpr  # Autocalculated if not passed explicitly

    image: StrExpr  # ImageRef
    preset: OptStrExpr
    http: Optional[HTTPPort]

    entrypoint: OptStrExpr
    cmd: StrExpr

    volumes: Sequence[StrExpr]  # Sequence[VolumeRef]
    tags: AbstractSet[StrExpr]

    env: Mapping[str, StrExpr]
    working_directory: OptStrExpr

    life_span: OptFloatExpr
    # continue_on_error: bool
    # if: str -- skip conditionally


@dataclass(frozen=True)
class Batch:
    # A set of steps, used in non-interactive mode
    # All steps share the same implicit persistent disk volume

    id: str
    title: OptStrExpr  # Autocalculated if not passed explicitly
    needs: List[StrExpr]  # BatchRef
    steps: List[Step]

    # matrix? Do we need a build matrix? Yes probably.

    # outputs: Mapping[str, str] -- metadata for communicating between batches.
    # will be added later

    # defaults for steps
    name: StrExpr
    image: OptStrExpr  # ImageRef
    preset: OptStrExpr

    volumes: Sequence[StrExpr]  # Sequence[VolumeRef]
    tags: AbstractSet[StrExpr]

    env: Mapping[str, StrExpr]
    workdir: OptRemotePathExpr

    life_span: OptFloatExpr
    # continue_on_error: bool
    # if: str -- skip conditionally


@dataclass(frozen=True)
class BaseFlow:
    kind: Kind
    title: OptStrExpr  # explicitly set or defived from config file name.

    # cluster: str  # really need it?

    images: Sequence[Image]
    volumes: Sequence[Volume]

    tags: AbstractSet[StrExpr]

    env: Mapping[str, StrExpr]
    workdir: OptRemotePathExpr

    life_span: OptFloatExpr


@dataclass(frozen=True)
class InteractiveFlow(BaseFlow):
    # self.kind == Kind.Job
    jobs: Mapping[str, Job]


@dataclass(frozen=True)
class BatchFlow(BaseFlow):
    # self.kind == Kind.Batch
    batches: Mapping[str, Batch]
