# Dataclasses
import enum
from dataclasses import dataclass
from typing import AbstractSet, List, Mapping, Sequence

from .expr import (
    BoolExpr,
    LocalPathExpr,
    OptBoolExpr,
    OptFloatExpr,
    OptIntExpr,
    OptLocalPathExpr,
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
    read_only: BoolExpr  # True if mounted in read-only mode, False for read-write
    local: OptLocalPathExpr


@dataclass(frozen=True)
class Image:
    id: str
    uri: URIExpr
    context: LocalPathExpr
    dockerfile: LocalPathExpr
    build_args: Mapping[str, StrExpr]


@dataclass(frozen=True)
class ExecUnit:
    title: OptStrExpr  # Autocalculated if not passed explicitly
    name: OptStrExpr
    image: StrExpr
    preset: OptStrExpr
    entrypoint: OptStrExpr
    cmd: OptStrExpr
    workdir: OptRemotePathExpr
    env: Mapping[str, StrExpr]
    volumes: Sequence[StrExpr]  # Sequence[VolumeRef]
    tags: AbstractSet[StrExpr]
    life_span: OptFloatExpr
    http_port: OptIntExpr
    http_auth: OptBoolExpr


@dataclass(frozen=True)
class Job(ExecUnit):
    # Interactive job used by Kind.Live flow
    id: str

    detach: BoolExpr
    browse: BoolExpr


@dataclass(frozen=True)
class Step(ExecUnit):
    # A step of a batch
    id: str

    image: StrExpr  # ImageRef
    preset: OptStrExpr

    entrypoint: OptStrExpr
    cmd: OptStrExpr

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
    name: OptStrExpr
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
class FlowDefaults:
    tags: AbstractSet[StrExpr]

    env: Mapping[str, StrExpr]
    workdir: OptRemotePathExpr

    life_span: OptFloatExpr

    preset: OptStrExpr


@dataclass(frozen=True)
class BaseFlow:
    kind: Kind
    # explicitly set or defived from config file name.
    # The name is used as default tags,
    # e.g. it works as flow.default.tags == [flow.name] if default.tags are not defined.
    # Note, flow.defaults is not changed actually but the calculation is applied
    # at contexts.Context creation level
    id: str

    title: OptStrExpr  # explicitly set or defived from config file name.

    # cluster: str  # really need it?

    images: Mapping[str, Image]
    volumes: Mapping[str, Volume]
    defaults: FlowDefaults


@dataclass(frozen=True)
class InteractiveFlow(BaseFlow):
    # self.kind == Kind.Job
    jobs: Mapping[str, Job]


@dataclass(frozen=True)
class BatchFlow(BaseFlow):
    # self.kind == Kind.Batch
    batches: Mapping[str, Batch]
