# Contexts
from dataclasses import dataclass, replace
from typing import AbstractSet, Mapping, Optional, Sequence

from yarl import URL

from . import ast
from .expr import ContainerT, RootABC, TypeT
from .types import LocalPath, RemotePath


# neuro -- global settings (cluster, user, api entrypoint)

# env -- Contains environment variables set in a workflow, job, or step

# job -- Information about the currently executing job

# batch -- Information about the currently executing batch

# steps -- Information about the steps that have been run in this job

# secrets -- Enables access to secrets.
#
# Do we want the explicit secrets support?  Perhaps better to have the secrets
# substitution on the client's cluster side (even not on the platform-api).

# strategy -- Enables access to the configured strategy parameters and information about
# the current job.
#
# Strategy parameters include batch-index, batch-total, (and maybe fail-fast and
# max-parallel).

# matrix -- Enables access to the matrix parameters you configured for the current job.

# needs -- Enables access to the outputs of all jobs that are defined as a dependency of
# the current job.

# images -- Enables access to image specifications.

# volumes -- Enables access to volume specifications.


class NotAvailable(LookupError):
    def __init__(self, ctx_name: str) -> None:
        super().__init__(f"Context {ctx_name} is not available")


class UnknownJob(KeyError):
    pass


@dataclass(frozen=True)
class Neuro:
    pass


@dataclass(frozen=True)
class ExecUnitCtx:
    title: Optional[str]
    name: str
    image: str
    preset: Optional[str]
    http_port: Optional[int]
    http_auth: Optional[bool]
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
class VolumeCtx:
    id: str
    uri: URL
    mount: RemotePath
    ro: bool


@dataclass(frozen=True)
class ImageCtx:
    id: str
    uri: URL
    context: LocalPath
    dockerfile: LocalPath
    build_args: Mapping[str, str]


@dataclass(frozen=True)
class Context(RootABC):
    _flow: ast.BaseFlow
    _job: Optional[JobCtx]
    _batch: Optional[BatchCtx]

    _volumes: Optional[Mapping[str, VolumeCtx]]
    _images: Optional[Mapping[str, ImageCtx]]

    _tags: AbstractSet[str]
    _env: Mapping[str, str]
    _workdir: Optional[RemotePath]
    _life_span: Optional[float]

    # Add a context with global flow info, e.g. ctx.flow.id maybe?

    @classmethod
    async def create(cls, flow: ast.BaseFlow) -> "Context":
        defaults = flow.defaults
        tags = defaults.tags if defaults.tags else {flow.id}
        ctx = cls(
            _flow=flow,
            _tags=tags,
            _env=defaults.env,
            _workdir=defaults.workdir,
            _life_span=defaults.life_span,
            _job=None,
            _batch=None,
            _volumes=None,
            _images=None,
        )

        # volumes / images needs a context with defaults only for self initialization
        volumes = {
            v: VolumeCtx(
                id=v.id,
                uri=await v.uri.eval(ctx),
                mount=await v.mount.eval(ctx),
                ro=await v.ro.eval(ctx),
            )
            for v in flow.volumes.values()
        }
        images = {
            i: ImageCtx(
                id=i.id,
                uri=await i.uri.eval(ctx),
                context=await i.context.eval(ctx),
                dockerfile=await i.dockerfile.eval(ctx),
                build_args={k: await v.eval(ctx) for k, v in i.build_args.items()},
            )
            for i in flow.images.values()
        }
        return replace(ctx, _volumes=volumes, _images=images)

    def lookup(self, name: str) -> TypeT:
        if name not in ("flow", "job", "batch", "volumes", "images"):
            raise NotAvailable(name)
        ret = getattr(self, name)
        assert isinstance(ret, ContainerT)
        return ret

    @property
    def env(self) -> Mapping[str, str]:
        return self._env

    @property
    def job(self) -> JobCtx:
        if self._job is None:
            raise NotAvailable("job")
        return self._job

    async def with_job(self, job_id: str) -> "Context":
        if self._job is not None:
            raise TypeError(
                "Cannot enter into the job context, if job is already initialized"
            )
        if self._batch is not None:
            raise TypeError(
                "Cannot enter into the job context if batch is already initialized"
            )
        if not isinstance(self._flow, ast.InteractiveFlow):
            raise TypeError(
                "Cannot enter into the job context for non-interactive flow"
            )
        try:
            job = self._flow.jobs[job_id]
        except KeyError:
            raise UnknownJob(job_id)

        tags = self._tags | {await v.eval(self) for v in job.tags}

        env = dict(self._env)
        env.update({k: await v.eval(self) for k, v in job.env.items()})

        workdir = (await job.workdir.eval(self)) or self._workdir
        life_span = (await job.life_span.eval(self)) or self._life_span

        job_ctx = JobCtx(
            id=job.id,
            detach=await job.detach.eval(self),
            browse=await job.browse.eval(self),
            title=(await job.title.eval(self)) or job.id,
            name=(await job.name.eval(self)) or job.id,
            image=await job.image.eval(self),
            preset=await job.preset.eval(self),
            entrypoint=await job.entrypoint.eval(self),
            cmd=await job.cmd.eval(self),
            workdir=workdir,
            env=env,
            volumes=[await v.eval(self) for v in job.volumes],
            tags=tags,
            life_span=life_span,
            http_port=await job.http_port.eval(self),
            http_auth=await job.http_auth.eval(self),
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
            raise NotAvailable("batch")
        return self._batch

    @property
    def volumes(self) -> Mapping[str, VolumeCtx]:
        if self._volumes is None:
            raise NotAvailable("volumes")
        return self._volumes

    @property
    def images(self) -> Mapping[str, ImageCtx]:
        if self._images is None:
            raise NotAvailable("images")
        return self._images
