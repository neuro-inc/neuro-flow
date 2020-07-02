# Contexts
from dataclasses import dataclass, field, fields, is_dataclass, replace
from typing import AbstractSet, Any, Dict, List, Mapping, Optional, Sequence, Set, cast

from . import ast
from .expr import Literal, LookupABC
from .types import RemotePath


# neuro -- global settings (cluster, user, api entrypoint)

# env -- Contains environment variables set in a workflow, job, or step

# job -- Information about the currently executing job

# batch -- Information about the currently executing batch

# steps -- Information about the steps that have been run in this job

# secrets -- Enables access to secrets.

# strategy -- Enables access to the configured strategy parameters and information about
# the current job.
# Strategy parameters include batch-index, batch-total,
# (and maybe fail-fast and max-parallel).

# matrix -- Enables access to the matrix parameters you configured for the current job.

# needs -- Enables access to the outputs of all jobs that are defined as a dependency of
# the current job.

# images -- Enables access to image specifications.

# volumes -- Enables access to volume specifications.


class InavailableContext(LookupError):
    def __init__(self, ctx_name: str) -> None:
        super().__init__(f"Context {ctx_name} is not available")


@dataclass(frozen=True)
class Neuro:
    pass


@dataclass(frozen=True)
class ExecUnitCtx:
    title: Optional[str]
    name: str
    image: str
    preset: Optional[str]
    # http: Optional[HTTPPort]
    entrypoint: Optional[str]
    cmd: str
    workdir: Optional[RemotePath]
    env: Mapping[str, str]
    volumes: Sequence[str]  # Sequence[VolumeRef]
    tags: AbstractSet[str]
    life_span: Optional[float]


@dataclass(frozen=True)
class JobCtx(ExecUnitCtx):
    id: str
    detach: bool
    browse: bool


@dataclass(frozen=True)
class BatchCtx:
    pass


@dataclass(frozen=True)
class Context(LookupABC):
    _job: Optional[JobCtx] = None
    _batch: Optional[BatchCtx] = None

    _tags: Set[str] = field(default_factory=set)
    _env: Dict[str, str] = field(default_factory=dict)
    _workdir: Optional[RemotePath] = None
    _life_span: Optional[float] = None

    def lookup(self, names: Sequence[str]) -> Literal:
        stack: List[str] = []
        current: Any = self

        for name in names:
            if name.startswith("_"):
                raise InavailableContext(".".join(stack))

            if is_dataclass(current):
                stack.append(name)
                for fld in fields(current):
                    if fld.name == name:
                        break
                else:
                    raise InavailableContext(".".join(stack))
            elif isinstance(current, dict):
                pass
            else:
                raise LookupError(
                    f"{'.'.join(stack)} is a terminal, cannot get subcontext {name}"
                )

            try:
                current = getattr(current, name)
            except AttributeError:
                raise InavailableContext(".".join(stack))

        if is_dataclass(current):
            # TODO: recursively replace with dict of plain values
            # to support compound objects
            raise LookupError(f"{'.'.join(stack)} is not a terminal")

        return cast(Literal, current)

    @property
    def env(self) -> Mapping[str, str]:
        return self._env

    @property
    def job(self) -> JobCtx:
        if self._job is None:
            raise InavailableContext("job")
        return self._job

    def with_job(self, job: ast.Job) -> "Context":
        if self._job is not None:
            raise TypeError(
                "Cannot enter into the job context, if job is already initialized"
            )
        if self._batch is not None:
            raise TypeError(
                "Cannot enter into the job context if batch is already initialized"
            )
        tags = self._tags | {v.eval(self) for v in job.tags}

        env = self._env.copy()
        env.update({k: v.eval(self) for k, v in job.env.items()})

        workdir = job.workdir.eval(self) or self._workdir
        life_span = job.life_span.eval(self) or self._life_span

        job_ctx = JobCtx(
            id=job.id,
            detach=job.detach.eval(self),
            browse=job.browse.eval(self),
            title=job.title.eval(self) or job.id,
            name=job.name.eval(self) or job.id,
            image=job.image.eval(self),
            preset=job.preset.eval(self),
            entrypoint=job.entrypoint.eval(self),
            cmd=job.cmd.eval(self),
            workdir=workdir,
            env=env,
            volumes=[v.eval(self) for v in job.volumes],
            tags=tags,
            life_span=life_span,
        )
        return replace(
            self,
            _job=job_ctx,
            _tags=tags,
            _env=env,
            _workdir=workdir,
            _life_span=life_span,
        )

    @property
    def batch(self) -> BatchCtx:
        if self._batch is None:
            raise InavailableContext("batch")
        return self._batch
