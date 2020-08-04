# Dataclasses
from dataclasses import dataclass

import enum
from typing import Mapping, Optional, Sequence

from .expr import (
    IdExpr,
    OptBoolExpr,
    OptIdExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptLocalPathExpr,
    OptRemotePathExpr,
    OptStrExpr,
    PortPairExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)
from .tokenizer import Pos
from .types import LocalPath


@dataclass(frozen=True)
class Base:
    _start: Pos
    _end: Pos


# There are 'batch' for pipelined mode and 'live' for interactive one
# (while 'batches' are technically just non-interactive jobs.


class Kind(enum.Enum):
    LIVE = "live"  # interactive mode.
    BATCH = "batch"  # pipelined mode


@dataclass(frozen=True)
class Volume(Base):
    remote: URIExpr  # remote URI, e.g. storage:folder/subfolder
    mount: RemotePathExpr  # mount path inside container
    local: OptLocalPathExpr
    read_only: OptBoolExpr  # True if mounted in read-only mode, False for read-write


@dataclass(frozen=True)
class Image(Base):
    ref: StrExpr  # Image reference, e.g. image:my-proj or neuromation/base@v1.6
    context: OptLocalPathExpr
    dockerfile: OptLocalPathExpr
    build_args: Optional[Sequence[StrExpr]]


@dataclass(frozen=True)
class ExecUnit(Base):
    title: OptStrExpr  # Autocalculated if not passed explicitly
    name: OptStrExpr
    image: StrExpr
    preset: OptStrExpr
    entrypoint: OptStrExpr
    cmd: OptStrExpr
    workdir: OptRemotePathExpr
    env: Optional[Mapping[str, StrExpr]]
    volumes: Optional[Sequence[StrExpr]]
    tags: Optional[Sequence[StrExpr]]
    life_span: OptLifeSpanExpr
    http_port: OptIntExpr
    http_auth: OptBoolExpr


@dataclass(frozen=True)
class Matrix(Base):
    # AST class is slightly different from YAML representation,
    # in YAML `products` mapping is embedded into the matrix itself.
    products: Mapping[str, Sequence[StrExpr]]
    exclude: Sequence[Mapping[str, StrExpr]]
    include: Sequence[Mapping[str, StrExpr]]


@dataclass(frozen=True)
class Strategy(Base):
    matrix: Matrix
    fail_fast: OptBoolExpr
    max_parallel: OptIntExpr


@dataclass(frozen=True)
class Job(ExecUnit):
    # Interactive job used by Kind.Live flow

    detach: OptBoolExpr
    browse: OptBoolExpr
    port_forward: Optional[Sequence[PortPairExpr]]


@dataclass(frozen=True)
class Task(ExecUnit):
    id: OptIdExpr

    # A set of steps, used in net mode
    # All steps share the same implicit persistent disk volume

    needs: Optional[Sequence[IdExpr]]  # BatchRef

    # matrix? Do we need a build matrix? Yes probably.

    strategy: Optional[Strategy]

    # continue_on_error: OptBoolExpr
    # if_: OptBoolExpr  # -- skip conditionally


@dataclass(frozen=True)
class FlowDefaults(Base):
    tags: Optional[Sequence[StrExpr]]

    env: Optional[Mapping[str, StrExpr]]
    workdir: OptRemotePathExpr

    life_span: OptLifeSpanExpr

    preset: OptStrExpr


# @dataclass(frozen=True)
# class BatchFlowDefaults(FlowDefaults):
#     fail_fast: OptBoolExpr
#     max_parallel: OptIntExpr


@dataclass(frozen=True)
class BaseFlow(Base):
    kind: Kind
    id: str
    workspace: LocalPath

    title: Optional[str]

    images: Optional[Mapping[str, Image]]
    volumes: Optional[Mapping[str, Volume]]
    defaults: Optional[FlowDefaults]


@dataclass(frozen=True)
class LiveFlow(BaseFlow):
    # self.kind == Kind.Job
    jobs: Mapping[str, Job]


@dataclass(frozen=True)
class BatchFlow(BaseFlow):
    # self.kind == Kind.Batch
    tasks: Sequence[Task]
