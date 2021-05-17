# Dataclasses
from dataclasses import dataclass, field

import enum
from typing import Mapping, Optional, Sequence, Union

from .expr import (
    BaseExpr,
    EnableExpr,
    IdExpr,
    MappingT,
    OptBoolExpr,
    OptIdExpr,
    OptIntExpr,
    OptLocalPathExpr,
    OptRemotePathExpr,
    OptStrExpr,
    OptTimeDeltaExpr,
    RemotePathExpr,
    SequenceT,
    SimpleIdExpr,
    SimpleOptBoolExpr,
    SimpleOptIdExpr,
    SimpleOptStrExpr,
    SimpleStrExpr,
    StrExpr,
    URIExpr,
)
from .tokenizer import Pos


@dataclass(frozen=True)
class Base:
    _start: Pos
    _end: Pos


class CacheStrategy(enum.Enum):
    NONE = "none"
    DEFAULT = "default"
    INHERIT = "inherit"


@dataclass(frozen=True)
class Cache(Base):
    # 'default' for root BatchFlowDefaults,
    # 'inherit' for task definitions and actions
    strategy: Optional[CacheStrategy] = field(metadata={"allow_none": True})
    life_span: OptTimeDeltaExpr
    # TODO: maybe add extra key->value mapping for additional cache keys later


@dataclass(frozen=True)
class Project(Base):
    id: SimpleIdExpr


# There are 'batch' for pipelined mode and 'live' for interactive one
# (while 'batches' are technically just non-interactive jobs.


class FlowKind(enum.Enum):
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
    build_args: Optional[BaseExpr[SequenceT]] = field(metadata={"allow_none": True})
    env: Optional[BaseExpr[MappingT]] = field(metadata={"allow_none": True})
    volumes: Optional[BaseExpr[SequenceT]] = field(metadata={"allow_none": True})
    build_preset: OptStrExpr


@dataclass(frozen=True)
class ExecUnit(Base):
    title: OptStrExpr  # Autocalculated if not passed explicitly
    name: OptStrExpr
    image: StrExpr
    preset: OptStrExpr
    schedule_timeout: OptTimeDeltaExpr
    entrypoint: OptStrExpr
    cmd: OptStrExpr
    workdir: OptRemotePathExpr
    env: Optional[BaseExpr[MappingT]] = field(metadata={"allow_none": True})
    volumes: Optional[BaseExpr[SequenceT]] = field(metadata={"allow_none": True})
    tags: Optional[BaseExpr[SequenceT]] = field(metadata={"allow_none": True})
    life_span: OptTimeDeltaExpr
    http_port: OptIntExpr
    http_auth: OptBoolExpr
    pass_config: OptBoolExpr


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
class Param(Base):
    # Possible params in yaml:
    # params:
    #  name: ~
    #  name: value
    #  name:
    #    default: value
    #    descr: description
    default: SimpleOptStrExpr
    descr: SimpleOptStrExpr


@dataclass(frozen=True)
class JobBase(Base):
    params: Optional[Mapping[str, Param]] = field(metadata={"allow_none": True})


@dataclass(frozen=True)
class Job(ExecUnit, JobBase):
    # Interactive job used by Kind.Live flow

    detach: OptBoolExpr
    browse: OptBoolExpr
    port_forward: Optional[BaseExpr[SequenceT]] = field(metadata={"allow_none": True})
    multi: SimpleOptBoolExpr


class NeedsLevel(enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"  # pipelined mode


@dataclass(frozen=True)
class TaskBase(Base):
    id: OptIdExpr

    # A set of steps, used in net mode
    # All steps share the same implicit persistent disk volume

    needs: Optional[Mapping[IdExpr, NeedsLevel]] = field(metadata={"allow_none": True})

    # matrix? Do we need a build matrix? Yes probably.

    strategy: Optional[Strategy] = field(metadata={"allow_none": True})

    # continue_on_error: OptBoolExpr
    enable: EnableExpr = field(metadata={"default_expr": "${{ success() }}"})
    cache: Optional[Cache] = field(metadata={"allow_none": True})


@dataclass(frozen=True)
class Task(ExecUnit, TaskBase):
    pass


@dataclass(frozen=True)
class BaseActionCall(Base):
    action: SimpleStrExpr  # action ref
    args: Optional[Mapping[str, StrExpr]] = field(metadata={"allow_none": True})


@dataclass(frozen=True)
class JobActionCall(BaseActionCall, JobBase):
    pass


@dataclass(frozen=True)
class TaskActionCall(BaseActionCall, TaskBase):
    enable: EnableExpr = field(metadata={"default_expr": "${{ success() }}"})
    cache: Optional[Cache] = field(metadata={"allow_none": True})


@dataclass(frozen=True)
class FlowDefaults(Base):
    tags: Optional[BaseExpr[SequenceT]] = field(metadata={"allow_none": True})

    env: Optional[BaseExpr[MappingT]] = field(metadata={"allow_none": True})
    volumes: Optional[BaseExpr[SequenceT]] = field(metadata={"allow_none": True})
    workdir: OptRemotePathExpr

    life_span: OptTimeDeltaExpr

    preset: OptStrExpr
    schedule_timeout: OptTimeDeltaExpr


@dataclass(frozen=True)
class BatchFlowDefaults(FlowDefaults):
    fail_fast: OptBoolExpr
    max_parallel: OptIntExpr
    cache: Optional[Cache] = field(metadata={"allow_none": True})


@dataclass(frozen=True)
class BaseFlow(Base):
    kind: FlowKind
    id: SimpleOptIdExpr

    title: SimpleOptStrExpr

    images: Optional[Mapping[str, Image]] = field(metadata={"allow_none": True})
    volumes: Optional[Mapping[str, Volume]] = field(metadata={"allow_none": True})
    defaults: Optional[FlowDefaults] = field(metadata={"allow_none": True})


@dataclass(frozen=True)
class LiveFlow(BaseFlow):
    # self.kind == Kind.Job
    jobs: Mapping[str, Union[Job, JobActionCall]]


@dataclass(frozen=True)
class BatchFlow(BaseFlow):
    # self.kind == Kind.Batch
    life_span: OptTimeDeltaExpr = field(metadata={"allow_none": True})
    params: Optional[Mapping[str, Param]] = field(metadata={"allow_none": True})
    tasks: Sequence[Union[Task, TaskActionCall]]

    defaults: Optional[BatchFlowDefaults] = field(metadata={"allow_none": True})


# Action


class ActionKind(enum.Enum):
    LIVE = "live"  # live composite
    BATCH = "batch"  # batch composite
    STATEFUL = "stateful"  # stateful, can be used in batch flow
    LOCAL = "local"  # runs locally, can be used in batch flow


@dataclass(frozen=True)
class Input(Base):
    descr: SimpleOptStrExpr
    default: SimpleOptStrExpr


@dataclass(frozen=True)
class Output(Base):
    descr: SimpleOptStrExpr
    # TODO: split Output class to BatchOutput with value and an Output without it
    value: OptStrExpr  # valid for BatchAction only


@dataclass(frozen=True)
class BaseAction(Base):
    name: SimpleOptStrExpr
    author: SimpleOptStrExpr
    descr: SimpleOptStrExpr
    inputs: Optional[Mapping[str, Input]] = field(metadata={"allow_none": True})

    kind: ActionKind


@dataclass(frozen=True)
class LiveAction(BaseAction):
    job: Job


@dataclass(frozen=True)
class BatchActionOutputs(Base):
    # AST class is slightly different from YAML representation,
    # in YAML `values` mapping is embedded into the outputs itself.
    values: Optional[Mapping[str, Output]] = field(metadata={"allow_none": True})


@dataclass(frozen=True)
class BatchAction(BaseAction):
    outputs: Optional[BatchActionOutputs] = field(metadata={"allow_none": True})
    cache: Optional[Cache] = field(metadata={"allow_none": True})

    tasks: Sequence[Task]


@dataclass(frozen=True)
class StatefulAction(BaseAction):
    outputs: Optional[Mapping[str, Output]] = field(metadata={"allow_none": True})
    main: ExecUnit
    post: Optional[ExecUnit] = field(metadata={"allow_none": True})
    post_if: EnableExpr = field(metadata={"default_expr": "${{ always() }}"})


@dataclass(frozen=True)
class LocalAction(BaseAction):
    outputs: Optional[Mapping[str, Output]] = field(metadata={"allow_none": True})
    cmd: StrExpr
