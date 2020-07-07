# Contexts
from dataclasses import dataclass, replace
from typing import AbstractSet, Mapping, Optional, Sequence

from yarl import URL

from . import ast
from .expr import ContainerT, MappingT, RootABC, SequenceT, TypeT
from .types import LocalPath, RemotePath


# Neuro-flow contexts (variables available during expressions calculation).

# The basic design idea is: we should avoid nested contexts if possible.
#
# That's why there is `env` context but defaults.env and job.env are absent.
#
# During the calculation the `env` context is updated to reflect global envs and job's
# env accordingly. This design principle makes expressions shorter in yaml file.  Short
# expressions are super important since the expression syntax has no user-defined
# variables.


# neuro -- global settings (cluster, user, api entrypoint)

# flow -- global flow settings, e.g. id

# defaults -- global flow defaults: env, preset, tags, workdir, life_span

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
    name: Optional[str]
    image: str
    preset: Optional[str]
    http_port: Optional[int]
    http_auth: Optional[bool]
    entrypoint: Optional[str]
    cmd: Optional[str]
    workdir: Optional[RemotePath]
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
    read_only: bool
    local: Optional[LocalPath]

    @property
    def ro_volume(self) -> str:
        return f"{self.uri}:{self.mount}:ro"

    @property
    def rw_volume(self) -> str:
        return f"{self.uri}:{self.mount}:rw"

    @property
    def volume(self) -> str:
        ro = "ro" if self.read_only else "rw"
        return f"{self.uri}:{self.mount}:{ro}"


@dataclass(frozen=True)
class ImageCtx:
    id: str
    uri: URL
    context: LocalPath
    dockerfile: LocalPath
    build_args: Mapping[str, str]


@dataclass(frozen=True)
class DefaultsCtx:
    tags: AbstractSet[str]
    workdir: Optional[RemotePath]
    life_span: Optional[float]
    preset: Optional[str]


@dataclass(frozen=True)
class FlowCtx:
    id: str


@dataclass(frozen=True)
class Context(RootABC):
    _flow_ast: ast.BaseFlow
    flow: FlowCtx
    _defaults: Optional[DefaultsCtx]
    _env: Optional[Mapping[str, str]]

    _images: Optional[Mapping[str, ImageCtx]]
    _volumes: Optional[Mapping[str, VolumeCtx]]

    _job: Optional[JobCtx]
    _batch: Optional[BatchCtx]

    # Add a context with global flow info, e.g. ctx.flow.id maybe?

    @classmethod
    async def create(cls, flow_ast: ast.BaseFlow) -> "Context":
        flow = FlowCtx(id=flow_ast.id)

        ctx = cls(
            _flow_ast=flow_ast,
            flow=flow,
            _env=None,
            _defaults=None,
            _images=None,
            _volumes=None,
            _job=None,
            _batch=None,
        )

        env = {k: await v.eval(ctx) for k, v in flow_ast.defaults.env.items()}

        tags = {await t.eval(ctx) for t in flow_ast.defaults.tags}
        if not tags:
            tags = {f"flow:{flow.id}"}

        defaults = DefaultsCtx(
            tags=tags,
            workdir=await flow_ast.defaults.workdir.eval(ctx),
            life_span=await flow_ast.defaults.life_span.eval(ctx),
            preset=await flow_ast.defaults.preset.eval(ctx),
        )
        ctx = replace(ctx, _defaults=defaults, _env=env)

        # volumes / images needs a context with defaults only for self initialization
        volumes = {
            v.id: VolumeCtx(
                id=v.id,
                uri=await v.uri.eval(ctx),
                mount=await v.mount.eval(ctx),
                read_only=await v.read_only.eval(ctx),
                local=await v.local.eval(ctx),
            )
            for v in flow_ast.volumes.values()
        }
        images = {
            i.id: ImageCtx(
                id=i.id,
                uri=await i.uri.eval(ctx),
                context=await i.context.eval(ctx),
                dockerfile=await i.dockerfile.eval(ctx),
                build_args={k: await v.eval(ctx) for k, v in i.build_args.items()},
            )
            for i in flow_ast.images.values()
        }
        return replace(ctx, _volumes=volumes, _images=images)

    def lookup(self, name: str) -> TypeT:
        if name not in ("flow", "defaults", "volumes", "images", "env", "job", "batch"):
            raise NotAvailable(name)
        ret = getattr(self, name)
        assert isinstance(ret, (ContainerT, SequenceT, MappingT))
        return ret

    @property
    def env(self) -> Mapping[str, str]:
        if self._env is None:
            raise NotAvailable("env")
        return self._env

    @property
    def defaults(self) -> DefaultsCtx:
        if self._defaults is None:
            raise NotAvailable("defaults")
        return self._defaults

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
        if not isinstance(self._flow_ast, ast.InteractiveFlow):
            raise TypeError(
                "Cannot enter into the job context for non-interactive flow"
            )
        try:
            job = self._flow_ast.jobs[job_id]
        except KeyError:
            raise UnknownJob(job_id)

        tags = {await v.eval(self) for v in job.tags}
        if not tags:
            tags = {f"job:{job.id}"}

        env = dict(self.env)
        env.update({k: await v.eval(self) for k, v in job.env.items()})

        workdir = (await job.workdir.eval(self)) or self.defaults.workdir
        life_span = (await job.life_span.eval(self)) or self.defaults.life_span

        preset = (await job.preset.eval(self)) or self.defaults.preset

        job_ctx = JobCtx(
            id=job.id,
            detach=await job.detach.eval(self),
            browse=await job.browse.eval(self),
            title=(await job.title.eval(self)) or f"{self.flow.id}.{job.id}",
            name=(await job.name.eval(self)),
            image=await job.image.eval(self),
            preset=preset,
            entrypoint=await job.entrypoint.eval(self),
            cmd=await job.cmd.eval(self),
            workdir=workdir,
            volumes=[await v.eval(self) for v in job.volumes],
            tags=self.defaults.tags | tags,
            life_span=life_span,
            http_port=await job.http_port.eval(self),
            http_auth=await job.http_auth.eval(self),
        )
        return replace(self, _job=job_ctx, _env=env,)

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
