# Dataclasses
import enum
from dataclasses import dataclass
from typing import AbstractSet, List, Mapping, Optional, Sequence

from .expr import (
    OptBoolExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptLocalPathExpr,
    OptRemotePathExpr,
    OptStrExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)
from .types import LocalPath


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
    local: OptLocalPathExpr
    read_only: OptBoolExpr  # True if mounted in read-only mode, False for read-write


@dataclass(frozen=True)
class Image:
    id: str
    uri: URIExpr
    context: OptLocalPathExpr
    dockerfile: OptLocalPathExpr
    build_args: Sequence[StrExpr]


@dataclass(frozen=True)
class ExecUnit:
    title: OptStrExpr  # Autocalculated if not passed explicitly
    name: OptStrExpr
    image: StrExpr
    preset: OptStrExpr
    entrypoint: OptStrExpr
    cmd: OptStrExpr
    workdir: OptRemotePathExpr
    env: Optional[Mapping[str, StrExpr]]
    volumes: Optional[Sequence[StrExpr]]
    tags: Optional[AbstractSet[StrExpr]]
    life_span: OptLifeSpanExpr
    http_port: OptIntExpr
    http_auth: OptBoolExpr


@dataclass(frozen=True)
class Job(ExecUnit):
    # Interactive job used by Kind.Live flow
    id: str

    detach: OptBoolExpr
    browse: OptBoolExpr


@dataclass(frozen=True)
class Step(ExecUnit):
    # A step of a batch
    id: str

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

    volumes: Optional[Sequence[StrExpr]]
    tags: Optional[AbstractSet[StrExpr]]

    env: Optional[Mapping[str, StrExpr]]
    workdir: OptRemotePathExpr

    life_span: OptLifeSpanExpr
    # continue_on_error: bool
    # if: str -- skip conditionally


@dataclass(frozen=True)
class FlowDefaults:
    tags: Optional[AbstractSet[StrExpr]]

    env: Optional[Mapping[str, StrExpr]]
    workdir: OptRemotePathExpr

    life_span: OptLifeSpanExpr

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
    workspace: LocalPath

    title: OptStrExpr  # explicitly set or defived from config file name.

    # cluster: str  # really need it?

    images: Optional[Mapping[str, Image]]
    volumes: Optional[Mapping[str, Volume]]
    defaults: Optional[FlowDefaults]


@dataclass(frozen=True)
class InteractiveFlow(BaseFlow):
    # self.kind == Kind.Job
    jobs: Mapping[str, Job]


@dataclass(frozen=True)
class BatchFlow(BaseFlow):
    # self.kind == Kind.Batch
    batches: Mapping[str, Batch]
