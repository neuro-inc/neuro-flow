# Contexts
from dataclasses import dataclass, field, replace

import enum
import itertools
from toposort import toposort
from typing import (
    AbstractSet,
    ClassVar,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    cast,
)
from yarl import URL

from . import ast
from .expr import LiteralT, RootABC, TypeT
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


class UnknownBatch(KeyError):
    pass


@dataclass(frozen=True)
class Neuro:
    pass


class Result(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DepCtx:
    result: Result
    outputs: Mapping[str, str]


NeedsCtx = Mapping[str, DepCtx]


MatrixCtx = Mapping[str, LiteralT]


@dataclass(frozen=True)
class StrategyCtx:
    fail_fast: bool = False
    max_parallel: int = 10


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
    port_forward: Sequence[str]


@dataclass(frozen=True)
class PreparedBatchCtx:
    id: Optional[str]
    real_id: str

    needs: AbstractSet[str]  # A set of batch.id
    matrix: MatrixCtx
    strategy: StrategyCtx

    ast: ast.Batch


@dataclass(frozen=True)
class BatchCtx(ExecUnitCtx):
    id: Optional[str]
    real_id: str

    needs: AbstractSet[str]  # A set of batch.id

    # matrix? Do we need a build matrix? Yes probably.

    # outputs: Mapping[str, str] -- metadata for communicating between batches.
    # will be added later

    # continue_on_error: OptBoolExpr
    # if_: OptBoolExpr  # -- skip conditionally


@dataclass(frozen=True)
class VolumeCtx:
    id: str
    remote: URL
    mount: RemotePath
    read_only: bool
    local: Optional[LocalPath]
    full_local_path: Optional[LocalPath]

    @property
    def ref_ro(self) -> str:
        return f"{self.remote}:{self.mount}:ro"

    @property
    def ref_rw(self) -> str:
        return f"{self.remote}:{self.mount}:rw"

    @property
    def ref(self) -> str:
        ro = "ro" if self.read_only else "rw"
        return f"{self.remote}:{self.mount}:{ro}"


@dataclass(frozen=True)
class ImageCtx:
    id: str
    ref: str
    context: Optional[LocalPath]
    full_context_path: Optional[LocalPath]
    dockerfile: Optional[LocalPath]
    full_dockerfile_path: Optional[LocalPath]
    build_args: Sequence[str]


@dataclass(frozen=True)
class DefaultsCtx:
    tags: AbstractSet[str]
    workdir: Optional[RemotePath]
    life_span: Optional[float]
    preset: Optional[str]


# @dataclass(frozen=True)
# class BatchDefaultsCtx(DefaultsCtx):
#     fail_fast: Optional[bool]
#     max_parallel: Optional[int]


@dataclass(frozen=True)
class FlowCtx:
    id: str
    workspace: LocalPath
    title: str


_CtxT = TypeVar("_CtxT", bound="BaseContext")


@dataclass(frozen=True)
class BaseContext(RootABC):
    FLOW_TYPE: ClassVar[Type[ast.BaseFlow]] = field(init=False)
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False,
        default=("flow", "defaults", "volumes", "images", "env", "job", "batch",),
    )

    _ast_flow: ast.BaseFlow
    flow: FlowCtx
    _defaults: Optional[DefaultsCtx] = None
    _env: Optional[Mapping[str, str]] = None

    _images: Optional[Mapping[str, ImageCtx]] = None
    _volumes: Optional[Mapping[str, VolumeCtx]] = None

    # Add a context with global flow info, e.g. ctx.flow.id maybe?

    @classmethod
    async def create(cls: Type[_CtxT], ast_flow: ast.BaseFlow) -> _CtxT:
        assert isinstance(ast_flow, cls.FLOW_TYPE)
        flow = FlowCtx(
            id=ast_flow.id,
            workspace=ast_flow.workspace.resolve(),
            title=ast_flow.title or ast_flow.id,
        )

        ctx = cls(_ast_flow=ast_flow, flow=flow,)

        ast_defaults = ast_flow.defaults
        if ast_defaults is not None:
            if ast_defaults.env is not None:
                env = {k: await v.eval(ctx) for k, v in ast_defaults.env.items()}
            else:
                env = {}

            if ast_defaults.tags is not None:
                tags = {await t.eval(ctx) for t in ast_defaults.tags}
            else:
                tags = set()
            workdir = await ast_defaults.workdir.eval(ctx)
            life_span = await ast_defaults.life_span.eval(ctx)
            preset = await ast_defaults.preset.eval(ctx)
        else:
            env = {}
            tags = set()
            workdir = None
            life_span = None
            preset = None

        if not tags:
            tags = {f"flow:{flow.id}"}

        defaults = DefaultsCtx(
            tags=tags, workdir=workdir, life_span=life_span, preset=preset,
        )
        ctx = replace(ctx, _defaults=defaults, _env=env)

        # volumes / images needs a context with defaults only for self initialization
        volumes = {}
        if ast_flow.volumes is not None:
            for k, v in ast_flow.volumes.items():
                local_path = await v.local.eval(ctx)
                volumes[k] = VolumeCtx(
                    id=k,
                    remote=await v.remote.eval(ctx),
                    mount=await v.mount.eval(ctx),
                    read_only=bool(await v.read_only.eval(ctx)),
                    local=local_path,
                    full_local_path=calc_full_path(ctx, local_path),
                )
        images = {}
        if ast_flow.images is not None:
            for k, i in ast_flow.images.items():
                context_path = await i.context.eval(ctx)
                dockerfile_path = await i.dockerfile.eval(ctx)
                if i.build_args is not None:
                    build_args = [await v.eval(ctx) for v in i.build_args]
                else:
                    build_args = []
                images[k] = ImageCtx(
                    id=k,
                    ref=await i.ref.eval(ctx),
                    context=context_path,
                    full_context_path=calc_full_path(ctx, context_path),
                    dockerfile=dockerfile_path,
                    full_dockerfile_path=calc_full_path(ctx, dockerfile_path),
                    build_args=build_args,
                )
        return replace(ctx, _volumes=volumes, _images=images)

    def lookup(self, name: str) -> TypeT:
        if name not in self.LOOKUP_KEYS:
            raise NotAvailable(name)
        ret = getattr(self, name)
        # assert isinstance(ret, (ContainerT, SequenceT, MappingT)), ret
        return cast(TypeT, ret)

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
    def volumes(self) -> Mapping[str, VolumeCtx]:
        if self._volumes is None:
            raise NotAvailable("volumes")
        return self._volumes

    @property
    def images(self) -> Mapping[str, ImageCtx]:
        if self._images is None:
            raise NotAvailable("images")
        return self._images


@dataclass(frozen=True)
class JobContext(BaseContext):
    FLOW_TYPE: ClassVar[Type[ast.LiveFlow]] = field(init=False, default=ast.LiveFlow)
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False, default=BaseContext.LOOKUP_KEYS + ("job",)
    )
    _job: Optional[JobCtx] = None

    @property
    def job(self) -> JobCtx:
        if self._job is None:
            raise NotAvailable("job")
        return self._job

    async def with_job(self, job_id: str) -> "JobContext":
        if self._job is not None:
            raise TypeError(
                "Cannot enter into the job context, if job is already initialized"
            )
        assert isinstance(self._ast_flow, self.FLOW_TYPE)

        try:
            job = self._ast_flow.jobs[job_id]
        except KeyError:
            raise UnknownJob(job_id)

        tags = set()
        if job.tags is not None:
            tags = {await v.eval(self) for v in job.tags}
        if not tags:
            tags = {f"job:{job_id}"}

        env = dict(self.env)
        if job.env is not None:
            env.update({k: await v.eval(self) for k, v in job.env.items()})

        title = await job.title.eval(self)
        if title is None:
            title = f"{self.flow.id}.{job_id}"

        workdir = (await job.workdir.eval(self)) or self.defaults.workdir

        volumes = []
        if job.volumes is not None:
            volumes = [await v.eval(self) for v in job.volumes]

        life_span = (await job.life_span.eval(self)) or self.defaults.life_span

        preset = (await job.preset.eval(self)) or self.defaults.preset
        port_forward = []
        if job.port_forward is not None:
            port_forward = [await val.eval(self) for val in job.port_forward]

        job_ctx = JobCtx(
            id=job_id,
            detach=bool(await job.detach.eval(self)),
            browse=bool(await job.browse.eval(self)),
            title=title,
            name=(await job.name.eval(self)),
            image=await job.image.eval(self),
            preset=preset,
            entrypoint=await job.entrypoint.eval(self),
            cmd=await job.cmd.eval(self),
            workdir=workdir,
            volumes=volumes,
            tags=self.defaults.tags | tags,
            life_span=life_span,
            http_port=await job.http_port.eval(self),
            http_auth=await job.http_auth.eval(self),
            port_forward=port_forward,
        )
        return replace(self, _job=job_ctx, _env=env,)


@dataclass(frozen=True)
class PipelineContext(BaseContext):
    FLOW_TYPE: ClassVar[Type[ast.PipelineFlow]] = field(
        init=False, default=ast.PipelineFlow
    )
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False,
        default=BaseContext.LOOKUP_KEYS + ("batch", "needs", "matrix", "strategy"),
    )
    _batch: Optional[BatchCtx] = None
    _needs: Optional[NeedsCtx] = None
    _prep_batches: Optional[Mapping[str, PreparedBatchCtx]] = None
    _order: Optional[Sequence[AbstractSet[str]]] = None
    _matrix: Optional[MatrixCtx] = None
    _strategy: Optional[StrategyCtx] = None

    @classmethod
    async def create(cls: Type[_CtxT], ast_flow: ast.BaseFlow) -> _CtxT:
        ctx = await super(cls, PipelineContext).create(ast_flow)
        assert isinstance(ctx._ast_flow, ast.PipelineFlow)
        prep_batches = {}
        last_needs: Set[str] = set()
        for num, ast_batch in enumerate(ctx._ast_flow.batches, 1):
            # eval matrix
            matrix: Sequence[MatrixCtx]
            strategy: StrategyCtx
            default_strategy = StrategyCtx()
            if ast_batch.strategy is not None:
                fail_fast = await ast_batch.strategy.fail_fast.eval(ctx)
                if fail_fast is None:
                    fail_fast = default_strategy.fail_fast
                max_parallel = await ast_batch.strategy.max_parallel.eval(ctx)
                if max_parallel is None:
                    max_parallel = default_strategy.max_parallel
                strategy = StrategyCtx(fail_fast=fail_fast, max_parallel=max_parallel,)
                if ast_batch.strategy.matrix is not None:
                    matrix = await ctx._build_matrix(ast_batch.strategy)
                    matrix = await ctx._exclude(ast_batch.strategy, matrix)
                    matrix = await ctx._include(ast_batch.strategy, matrix)
                else:
                    matrix = [{}]  # dummy
            else:
                strategy = default_strategy  # default
                matrix = [{}]  # dummy

            real_ids = set()
            for row in matrix:
                # make prep patch(es)
                matrix_ctx = await ctx.with_matrix(row)
                batch_id = await ast_batch.id.eval(matrix_ctx)
                if batch_id is None:
                    # Dash is not allowed in identifier, so the generated read id
                    # never clamps with user_provided one.
                    suffix = [str(row[k]) for k in sorted(row)]
                    real_id = "-".join(["batch", str(num), *suffix])
                else:
                    real_id = batch_id
                if real_id in prep_batches:
                    raise ValueError(f"Duplicated batch id {real_id}")
                if ast_batch.needs is not None:
                    needs = {await need.eval(matrix_ctx) for need in ast_batch.needs}
                else:
                    needs = last_needs

                prep = PreparedBatchCtx(
                    id=batch_id,
                    real_id=real_id,
                    needs=needs,
                    matrix=row,
                    strategy=strategy,
                    ast=ast_batch,
                )
                prep_batches[real_id] = prep
                real_ids.add(real_id)

            last_needs = real_ids

        to_sort: Dict[str, AbstractSet[str]] = {}
        for key, val in prep_batches.items():
            to_sort[key] = val.needs
        order = list(toposort(to_sort))

        return replace(  # type: ignore[return-value]
            ctx, _prep_batches=prep_batches, _order=order
        )

    @property
    def batch(self) -> BatchCtx:
        if self._batch is None:
            raise NotAvailable("batch")
        return self._batch

    @property
    def needs(self) -> NeedsCtx:
        if self._needs is None:
            raise NotAvailable("needs")
        return self._needs

    @property
    def matrix(self) -> MatrixCtx:
        if self._matrix is None:
            raise NotAvailable("matrix")
        return self._matrix

    @property
    def strategy(self) -> StrategyCtx:
        if self._strategy is None:
            raise NotAvailable("strategy")
        return self._strategy

    @property
    def order(self) -> Sequence[AbstractSet[str]]:
        # Batch names, sorted by the execution order.
        # Batches from each set in the list can be executed concurrently.
        assert self._order is not None
        return self._order

    def get_dep_ids(self, real_id: str) -> AbstractSet[str]:
        assert self._prep_batches is not None
        prep_batch = self._prep_batches[real_id]
        return prep_batch.needs

    async def with_matrix(self, matrix: MatrixCtx) -> "PipelineContext":
        if self._matrix is not None:
            raise TypeError(
                "Cannot enter into the matrix context if "
                "the matrix is already initialized"
            )
        return replace(self, _matrix=matrix)

    async def with_batch(self, real_id: str, *, needs: NeedsCtx,) -> "PipelineContext":
        # real_id -- the batch's real id
        #
        # outputs -- real_id -> (output_name -> value) mapping for all batch ids
        # enumerated in needs.
        #
        # TODO: multi-state batches require 'state' mapping (state_name -> value)
        assert self._prep_batches is not None

        if self._batch is not None:
            raise TypeError(
                "Cannot enter into the batch context if "
                "the batch is already initialized"
            )
        try:
            prep_batch = self._prep_batches[real_id]
        except KeyError:
            raise UnknownBatch(real_id)

        if needs.keys() != prep_batch.needs:
            extra = ",".join(needs.keys() - prep_batch.needs)
            missing = ",".join(prep_batch.needs - needs.keys())
            err = ["Error in 'needs':"]
            if extra:
                err.append(f"unexpected keys {extra}")
            if missing:
                err.append(f"missing keys {missing}")
            raise ValueError(" ".join(err))

        ctx = await self.with_matrix(prep_batch.matrix)

        env = dict(ctx.env)
        if prep_batch.ast.env is not None:
            env.update({k: await v.eval(ctx) for k, v in prep_batch.ast.env.items()})

        title = await prep_batch.ast.title.eval(ctx)
        if title is None:
            title = f"{ctx.flow.id}.{real_id}"
        title = await prep_batch.ast.title.eval(ctx)

        tags = set()
        if prep_batch.ast.tags is not None:
            tags = {await v.eval(ctx) for v in prep_batch.ast.tags}
        if not tags:
            tags = {f"batch:{real_id}"}

        workdir = (await prep_batch.ast.workdir.eval(ctx)) or ctx.defaults.workdir

        volumes = []
        if prep_batch.ast.volumes is not None:
            volumes = [await v.eval(ctx) for v in prep_batch.ast.volumes]

        life_span = (await prep_batch.ast.life_span.eval(ctx)) or ctx.defaults.life_span

        preset = (await prep_batch.ast.preset.eval(ctx)) or ctx.defaults.preset

        batch_ctx = BatchCtx(
            id=prep_batch.id,
            real_id=prep_batch.real_id,
            needs=prep_batch.needs,
            title=title,
            name=(await prep_batch.ast.name.eval(ctx)),
            image=await prep_batch.ast.image.eval(ctx),
            preset=preset,
            entrypoint=await prep_batch.ast.entrypoint.eval(ctx),
            cmd=await prep_batch.ast.cmd.eval(ctx),
            workdir=workdir,
            volumes=volumes,
            tags=ctx.defaults.tags | tags,
            life_span=life_span,
            http_port=await prep_batch.ast.http_port.eval(ctx),
            http_auth=await prep_batch.ast.http_auth.eval(ctx),
        )
        return replace(
            ctx, _batch=batch_ctx, _env=env, _needs=needs, _strategy=prep_batch.strategy
        )

    async def _build_matrix(self, strategy: ast.Strategy) -> Sequence[MatrixCtx]:
        assert strategy.matrix is not None
        products = []
        for k, lst in strategy.matrix.products.items():
            lst2 = [{k: await i.eval(self)} for i in lst]
            products.append(lst2)
        ret = []
        for row in itertools.product(*products):
            dct: Dict[str, LiteralT] = {}
            for elem in row:
                dct.update(elem)
            ret.append(dct)
        return ret

    async def _exclude(
        self, strategy: ast.Strategy, matrix: Sequence[MatrixCtx]
    ) -> Sequence[MatrixCtx]:
        assert strategy.matrix is not None
        exclude = []
        for dct in strategy.matrix.exclude:
            exclude.append({k: await v.eval(self) for k, v in dct.items()})
        ret = []
        for row in matrix:
            for exc in exclude:
                match = True
                for k, v in exc.items():
                    if row[k] != v:
                        match = False
                        break
                if not match:
                    ret.append(row)
        return ret

    async def _include(
        self, strategy: ast.Strategy, matrix: Sequence[MatrixCtx]
    ) -> Sequence[MatrixCtx]:
        assert strategy.matrix is not None
        ret = list(matrix)
        for dct in strategy.matrix.include:
            ret.append({k: await v.eval(self) for k, v in dct.items()})
        return ret


def calc_full_path(ctx: BaseContext, path: Optional[LocalPath]) -> Optional[LocalPath]:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return ctx.flow.workspace.joinpath(path).resolve()
