import dataclasses
from dataclasses import dataclass, fields, replace

import collections
import enum
import hashlib
import itertools
import json
import shlex
import sys
from abc import abstractmethod
from datetime import timedelta
from functools import lru_cache
from neuro_sdk import Client
from typing import (
    AbstractSet,
    Any,
    AsyncIterator,
    Dict,
    Generic,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)
from typing_extensions import Annotated
from yarl import URL

from neuro_flow import ast
from neuro_flow.config_loader import ConfigLoader
from neuro_flow.expr import (
    EnableExpr,
    EvalError,
    Expr,
    IdExpr,
    LiteralT,
    RootABC,
    TypeT,
)
from neuro_flow.types import AlwaysT, FullID, LocalPath, RemotePath, TaskStatus


if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager

# Exceptions


class NotAvailable(LookupError):
    def __init__(self, ctx_name: str) -> None:
        super().__init__(f"The '{ctx_name}' context is not available")


class UnknownJob(KeyError):
    pass


class UnknownTask(KeyError):
    pass


# ...Ctx types, they define parts that can be available in expressions


EnvCtx = Annotated[Mapping[str, str], "EnvCtx"]
TagsCtx = Annotated[AbstractSet[str], "TagsCtx"]
VolumesCtx = Annotated[Mapping[str, "VolumeCtx"], "VolumesCtx"]
ImagesCtx = Annotated[Mapping[str, "ImageCtx"], "ImagesCtx"]
InputsCtx = Annotated[Mapping[str, str], "InputsCtx"]
ParamsCtx = Annotated[Mapping[str, str], "ParamsCtx"]

NeedsCtx = Annotated[Mapping[str, "DepCtx"], "NeedsCtx"]
StateCtx = Annotated[Mapping[str, str], "StateCtx"]
MatrixCtx = Annotated[Mapping[str, LiteralT], "MatrixCtx"]


@dataclass(frozen=True)
class FlowCtx:
    flow_id: str
    project_id: str
    workspace: LocalPath
    title: str

    @property
    def id(self) -> str:
        # TODO: add a custom warning API to report with config file name and
        # line numbers instead of bare printing
        import click

        click.echo(  # type: ignore
            "flow.id attribute is deprecated, use flow.flow_id instead",
            fg="yellow",
        )
        return self.flow_id


@dataclass(frozen=True)
class BatchFlowCtx(FlowCtx):
    life_span: Optional[float]


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
    env: Mapping[str, str]
    volumes: Sequence[str]
    build_preset: Optional[str]


@dataclass(frozen=True)
class MultiCtx:
    args: str
    suffix: str


@dataclass(frozen=True)
class StrategyCtx:
    fail_fast: bool = True
    max_parallel: int = 10


@dataclass(frozen=True)
class DepCtx:
    result: TaskStatus
    outputs: Mapping[str, str]

    def __post_init__(self) -> None:
        assert (
            self.result != TaskStatus.CACHED
        ), "CACHED status should replaced with SUCCEEDED for expressions"


# Confs (similar to ..Ctx, but not available to expressions, only used
# during evaluation)


@dataclass(frozen=True)
class CacheConf:
    strategy: ast.CacheStrategy = ast.CacheStrategy.DEFAULT
    life_span: float = 14 * 24 * 3600


@dataclass(frozen=True)
class DefaultsConf:
    volumes: Sequence[str] = ()
    workdir: Optional[RemotePath] = None
    life_span: Optional[float] = None
    schedule_timeout: Optional[float] = None
    preset: Optional[str] = None


# Return dataclasses
# Returned by flow classes to provide data to runner/executor.


@dataclass(frozen=True)
class ExecUnit:
    title: Optional[str]
    name: Optional[str]
    image: str
    preset: Optional[str]
    schedule_timeout: Optional[float]
    http_port: Optional[int]
    http_auth: Optional[bool]
    pass_config: Optional[bool]
    entrypoint: Optional[str]
    cmd: Optional[str]
    workdir: Optional[RemotePath]
    volumes: Sequence[str]  # Sequence[VolumeRef]
    life_span: Optional[float]
    env: Mapping[str, str]
    tags: AbstractSet[str]


@dataclass(frozen=True)
class Job(ExecUnit):
    id: str
    detach: bool
    browse: bool
    port_forward: Sequence[str]
    multi: bool


@dataclass(frozen=True)
class Task(ExecUnit):
    # executed task
    id: Optional[str]

    # continue_on_error: Optional[bool]
    enable: Union[bool, AlwaysT]

    strategy: StrategyCtx
    cache: "CacheConf"

    caching_key: str


@dataclass(frozen=True)
class LocalTask:
    # executed task
    id: Optional[str]
    cmd: str


@dataclass(frozen=True)
class TaskMeta:
    enable: Union[bool, AlwaysT]

    strategy: StrategyCtx
    cache: "CacheConf"


@dataclass(frozen=True)
class JobMeta:
    # Metadata used for jobs lookup
    id: str
    multi: bool
    tags: AbstractSet[str]


# ...Context classes, used to complete container of what is available
# to expressions


class EmptyRoot(RootABC):
    def lookup(self, name: str) -> TypeT:
        raise NotAvailable(name)

    @asynccontextmanager
    async def client(self) -> AsyncIterator[Client]:
        raise RuntimeError("neuro API is not available in <empty> context")
        yield Client()  # fake lint to make the code a real async iterator


EMPTY_ROOT = EmptyRoot()


@dataclass(frozen=True)
class Context(RootABC):
    _client: Client

    def lookup(self, name: str) -> TypeT:
        for f in fields(self):
            if f.name != name:
                continue
            break
        else:
            raise NotAvailable(name)
        ret = getattr(self, name)
        # assert isinstance(ret, (ContainerT, SequenceT, MappingT)), ret
        return cast(TypeT, ret)

    @asynccontextmanager
    async def client(self) -> AsyncIterator[Client]:
        yield self._client


@dataclass(frozen=True)
class WithFlowContext(Context):
    flow: FlowCtx


@dataclass(frozen=True)
class WithEnvContext(Context):
    env: EnvCtx


@dataclass(frozen=True)
class LiveContextStep1(WithFlowContext, Context):
    def to_live_ctx(
        self, env: EnvCtx, tags: TagsCtx, volumes: VolumesCtx, images: ImagesCtx
    ) -> "LiveContext":
        return LiveContext(
            flow=self.flow,
            env=env,
            tags=tags,
            volumes=volumes,
            images=images,
            _client=self._client,
        )


@dataclass(frozen=True)
class LiveContext(WithEnvContext, LiveContextStep1):
    tags: TagsCtx
    volumes: VolumesCtx
    images: ImagesCtx

    def to_job_ctx(self, params: ParamsCtx) -> "LiveJobContext":
        return LiveJobContext(
            flow=self.flow,
            env=self.env,
            tags=self.tags,
            volumes=self.volumes,
            images=self.images,
            params=params,
            _client=self._client,
        )

    def to_multi_job_ctx(
        self, multi: MultiCtx, params: ParamsCtx
    ) -> "LiveMultiJobContext":
        return LiveMultiJobContext(
            flow=self.flow,
            env=self.env,
            tags=self.tags,
            volumes=self.volumes,
            images=self.images,
            multi=multi,
            params=params,
            _client=self._client,
        )


@dataclass(frozen=True)
class LiveJobContext(LiveContext):
    params: ParamsCtx


@dataclass(frozen=True)
class LiveMultiJobContext(LiveContext):
    multi: MultiCtx
    params: ParamsCtx


@dataclass(frozen=True)
class LiveActionContext(Context):
    inputs: InputsCtx


@dataclass(frozen=True)
class BatchContextStep1(WithFlowContext, Context):
    flow: BatchFlowCtx
    params: ParamsCtx

    def to_step_2(
        self, env: EnvCtx, tags: TagsCtx, volumes: VolumesCtx, images: ImagesCtx
    ) -> "BatchContextStep2":
        return BatchContextStep2(
            flow=self.flow,
            params=self.params,
            env=env,
            tags=tags,
            volumes=volumes,
            images=images,
            _client=self._client,
        )


@dataclass(frozen=True)
class BatchContextStep2(WithEnvContext, BatchContextStep1):
    tags: TagsCtx
    volumes: VolumesCtx
    images: ImagesCtx

    def to_batch_ctx(
        self,
        strategy: StrategyCtx,
    ) -> "BatchContext":
        return BatchContext(
            flow=self.flow,
            params=self.params,
            env=self.env,
            tags=self.tags,
            volumes=self.volumes,
            images=self.images,
            strategy=strategy,
            _client=self._client,
        )


class BaseBatchContext(Context):
    strategy: StrategyCtx

    @abstractmethod
    def to_matrix_ctx(
        self, strategy: StrategyCtx, matrix: MatrixCtx
    ) -> "BaseMatrixContext":
        pass


class BaseMatrixContext(BaseBatchContext):
    matrix: MatrixCtx

    @abstractmethod
    def to_task_ctx(self, needs: NeedsCtx, state: StateCtx) -> "BaseTaskContext":
        pass


@dataclass(frozen=True)
class MatrixOnlyContext(Context):
    matrix: MatrixCtx


class BaseTaskContext(BaseMatrixContext):
    strategy: StrategyCtx
    needs: NeedsCtx
    state: StateCtx


@dataclass(frozen=True)
class BatchContext(BaseBatchContext, BatchContextStep2):
    strategy: StrategyCtx

    def to_matrix_ctx(
        self, strategy: StrategyCtx, matrix: MatrixCtx
    ) -> "BatchMatrixContext":
        return BatchMatrixContext(
            flow=self.flow,
            params=self.params,
            env=self.env,
            tags=self.tags,
            volumes=self.volumes,
            images=self.images,
            strategy=strategy,
            matrix=matrix,
            _client=self._client,
        )


@dataclass(frozen=True)
class BatchMatrixContext(BaseMatrixContext, BatchContext):
    matrix: MatrixCtx

    def to_task_ctx(self, needs: NeedsCtx, state: StateCtx) -> "BatchTaskContext":
        return BatchTaskContext(
            flow=self.flow,
            params=self.params,
            env=self.env,
            tags=self.tags,
            volumes=self.volumes,
            images=self.images,
            strategy=self.strategy,
            matrix=self.matrix,
            needs=needs,
            state=state,
            _client=self._client,
        )


@dataclass(frozen=True)
class BatchTaskContext(BaseTaskContext, BatchMatrixContext):
    needs: NeedsCtx
    state: StateCtx


@dataclass(frozen=True)
class BatchActionContext(BaseBatchContext):
    inputs: InputsCtx
    strategy: StrategyCtx

    def to_matrix_ctx(
        self, strategy: StrategyCtx, matrix: MatrixCtx
    ) -> "BatchActionMatrixContext":
        return BatchActionMatrixContext(
            inputs=self.inputs,
            matrix=matrix,
            strategy=strategy,
            _client=self._client,
        )

    def to_outputs_ctx(self, needs: NeedsCtx) -> "BatchActionOutputsContext":
        return BatchActionOutputsContext(
            strategy=self.strategy,
            inputs=self.inputs,
            needs=needs,
            _client=self._client,
        )


@dataclass(frozen=True)
class BatchActionOutputsContext(BatchActionContext):
    needs: NeedsCtx


@dataclass(frozen=True)
class BatchActionMatrixContext(BaseMatrixContext, BatchActionContext):
    matrix: MatrixCtx
    strategy: StrategyCtx

    def to_task_ctx(self, needs: NeedsCtx, state: StateCtx) -> "BatchActionTaskContext":
        return BatchActionTaskContext(
            inputs=self.inputs,
            matrix=self.matrix,
            strategy=self.strategy,
            needs=needs,
            state=state,
            _client=self._client,
        )


@dataclass(frozen=True)
class BatchActionTaskContext(BaseTaskContext, BatchActionMatrixContext):
    needs: NeedsCtx
    state: StateCtx


@dataclass(frozen=True)
class StatefulActionContext(Context):
    inputs: InputsCtx


@dataclass(frozen=True)
class LocalActionContext(Context):
    inputs: InputsCtx


async def setup_flow_ctx(
    ctx: RootABC,
    ast_flow: ast.BaseFlow,
    config_name: str,
    config_loader: ConfigLoader,
) -> FlowCtx:
    flow_id = await ast_flow.id.eval(ctx)
    if flow_id is None:
        flow_id = config_name.replace("-", "_")

    project = await config_loader.fetch_project()
    project_id = await project.id.eval(ctx)
    flow_title = await ast_flow.title.eval(ctx)

    return FlowCtx(
        flow_id=flow_id,
        project_id=project_id,
        workspace=config_loader.workspace,
        title=flow_title or flow_id,
    )


async def setup_batch_flow_ctx(
    ctx: RootABC,
    ast_flow: ast.BatchFlow,
    config_name: str,
    config_loader: ConfigLoader,
) -> BatchFlowCtx:
    base_flow = await setup_flow_ctx(ctx, ast_flow, config_name, config_loader)
    life_span = await ast_flow.life_span.eval(ctx)
    return BatchFlowCtx(
        flow_id=base_flow.flow_id,
        project_id=base_flow.project_id,
        workspace=base_flow.workspace,
        title=base_flow.title,
        life_span=life_span,
    )


async def setup_defaults_env_tags_ctx(
    ctx: WithFlowContext,
    ast_defaults: Optional[ast.FlowDefaults],
) -> Tuple[DefaultsConf, EnvCtx, TagsCtx]:
    env: EnvCtx
    tags: TagsCtx
    volumes: List[str]
    if ast_defaults is not None:
        if ast_defaults.env is not None:
            tmp_env = await ast_defaults.env.eval(ctx)
            assert isinstance(tmp_env, dict)
            env = tmp_env
        else:
            env = {}

        if ast_defaults.tags is not None:
            tmp_tags = await ast_defaults.tags.eval(ctx)
            assert isinstance(tmp_tags, list)
            tags = set(tmp_tags)
        else:
            tags = set()

        if ast_defaults.volumes:
            tmp_volumes = await ast_defaults.volumes.eval(ctx)
            assert isinstance(tmp_volumes, list)
            volumes = []
            for volume in tmp_volumes:
                if volume:
                    volumes.append(volume)
        else:
            volumes = []
        workdir = await ast_defaults.workdir.eval(ctx)
        life_span = await ast_defaults.life_span.eval(ctx)
        preset = await ast_defaults.preset.eval(ctx)
        schedule_timeout = await ast_defaults.schedule_timeout.eval(ctx)
    else:
        env = {}
        tags = set()
        volumes = []
        workdir = None
        life_span = None
        preset = None
        schedule_timeout = None

    tags.add(f"project:{_id2tag(ctx.flow.project_id)}")
    tags.add(f"flow:{_id2tag(ctx.flow.flow_id)}")

    defaults = DefaultsConf(
        volumes=volumes,
        workdir=workdir,
        life_span=life_span,
        preset=preset,
        schedule_timeout=schedule_timeout,
    )
    return defaults, env, tags


def _calc_full_path(
    ctx: WithFlowContext, path: Optional[LocalPath]
) -> Optional[LocalPath]:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return ctx.flow.workspace.joinpath(path).resolve()


async def setup_volumes_ctx(
    ctx: WithFlowContext,
    ast_volumes: Optional[Mapping[str, ast.Volume]],
) -> VolumesCtx:
    volumes = {}
    if ast_volumes is not None:
        for k, v in ast_volumes.items():
            local_path = await v.local.eval(ctx)
            volumes[k] = VolumeCtx(
                id=k,
                remote=await v.remote.eval(ctx),
                mount=await v.mount.eval(ctx),
                read_only=bool(await v.read_only.eval(ctx)),
                local=local_path,
                full_local_path=_calc_full_path(ctx, local_path),
            )
    return volumes


async def setup_images_ctx(
    ctx: WithFlowContext,
    ast_images: Optional[Mapping[str, ast.Image]],
) -> ImagesCtx:
    images = {}
    if ast_images is not None:
        for k, i in ast_images.items():
            context_path = await i.context.eval(ctx)
            dockerfile_path = await i.dockerfile.eval(ctx)
            build_args: List[str] = []
            if i.build_args is not None:
                tmp_build_args = await i.build_args.eval(ctx)
                assert isinstance(tmp_build_args, list)
                build_args = tmp_build_args

            image_env: Dict[str, str] = {}
            if i.env is not None:
                tmp_env = await i.env.eval(ctx)
                assert isinstance(tmp_env, dict)
                image_env.update(tmp_env)

            image_volumes: List[str] = []
            if i.volumes is not None:
                tmp_volumes = await i.volumes.eval(ctx)
                assert isinstance(tmp_volumes, list)
                for volume in tmp_volumes:
                    if volume:
                        image_volumes.append(volume)

            images[k] = ImageCtx(
                id=k,
                ref=await i.ref.eval(ctx),
                context=context_path,
                full_context_path=_calc_full_path(ctx, context_path),
                dockerfile=dockerfile_path,
                full_dockerfile_path=_calc_full_path(ctx, dockerfile_path),
                build_args=build_args,
                env=image_env,
                volumes=image_volumes,
                build_preset=await i.build_preset.eval(ctx),
            )
    return images


async def validate_action_call(
    call_ast: ast.BaseActionCall,
    ast_inputs: Optional[Mapping[str, ast.Input]],
) -> None:
    if ast_inputs:
        supported_inputs = ast_inputs.keys()
        required_inputs = {
            input_name
            for input_name, input_ast in ast_inputs.items()
            if input_ast.default.pattern is None
        }
    else:
        supported_inputs = set()
        required_inputs = set()
    if call_ast.args:
        supplied_inputs = call_ast.args.keys()
    else:
        supplied_inputs = set()
    missing = required_inputs - supplied_inputs
    if missing:
        raise EvalError(
            f"Required input(s): {','.join(sorted(missing))}",
            call_ast._start,
            call_ast._end,
        )
    extra = supplied_inputs - supported_inputs
    if extra:
        raise EvalError(
            f"Unsupported input(s): {','.join(sorted(extra))}",
            call_ast._start,
            call_ast._end,
        )


async def setup_inputs_ctx(
    ctx: RootABC,
    call_ast: ast.BaseActionCall,  # Only used to generate errors
    ast_inputs: Optional[Mapping[str, ast.Input]],
) -> InputsCtx:
    await validate_action_call(call_ast, ast_inputs)
    if call_ast.args is None or ast_inputs is None:
        return {}
    inputs = {k: await v.eval(ctx) for k, v in call_ast.args.items()}
    for name, inp in ast_inputs.items():
        if name not in inputs and inp.default.pattern is not None:
            val = await inp.default.eval(EMPTY_ROOT)
            # inputs doesn't support expressions,
            # non-none pattern means non-none input
            assert val is not None
            inputs[name] = val
    return inputs


async def setup_params_ctx(
    ctx: RootABC,
    params: Optional[Mapping[str, str]],
    ast_params: Optional[Mapping[str, ast.Param]],
) -> ParamsCtx:
    if params is None:
        params = {}
    new_params = {}
    if ast_params is not None:
        for k, v in ast_params.items():
            value = params.get(k) or await v.default.eval(ctx)
            if value is None:
                raise EvalError(
                    f"Param {k} is not initialized and has no default value",
                    v._start,
                    v._end,
                )
            new_params[k] = value
    extra = params.keys() - new_params.keys()
    if extra:
        raise ValueError(
            f"Unsupported arg(s): {','.join(sorted(extra))}",
        )
    return new_params


async def setup_strategy_ctx(
    ctx: RootABC,
    ast_defaults: Optional[ast.BatchFlowDefaults],
) -> StrategyCtx:
    if ast_defaults is None:
        return StrategyCtx()
    fail_fast = await ast_defaults.fail_fast.eval(ctx)
    if fail_fast is None:
        fail_fast = StrategyCtx.fail_fast
    max_parallel = await ast_defaults.max_parallel.eval(ctx)
    if max_parallel is None:
        max_parallel = StrategyCtx.max_parallel
    return StrategyCtx(fail_fast=fail_fast, max_parallel=max_parallel)


async def setup_matrix(ast_matrix: Optional[ast.Matrix]) -> Sequence[MatrixCtx]:
    if ast_matrix is None:
        return [{}]
    # Init
    products = []
    for k, lst in ast_matrix.products.items():
        lst2 = [{k: await i.eval(EMPTY_ROOT)} for i in lst]
        products.append(lst2)
    matrices = []
    for row in itertools.product(*products):
        dct: Dict[str, LiteralT] = {}
        for elem in row:
            dct.update(elem)
        matrices.append(dct)
    # Exclude
    exclude = []
    for exc_spec in ast_matrix.exclude:
        exclude.append({k: await v.eval(EMPTY_ROOT) for k, v in exc_spec.items()})
    filtered = []
    for matrix in matrices:
        include = True
        for exc in exclude:
            match = True
            for k, v in exc.items():
                if matrix[k] != v:
                    match = False
                    break
            if match:
                include = False
                break
        if include:
            filtered.append(matrix)
    matrices = filtered
    # Include
    for inc_spec in ast_matrix.include:
        if inc_spec.keys() != ast_matrix.products.keys():
            additional = inc_spec.keys() - ast_matrix.products.keys()
            missing = ast_matrix.products.keys() - inc_spec.keys()
            raise EvalError(
                "Keys of entry in include list of matrix are not the "
                "same as matrix keys: "
                + (
                    f"additional keys: {','.join(sorted(additional))}"
                    if additional
                    else ""
                )
                + (f" , " if additional and missing else "")
                + (f"missing keys: {','.join(sorted(missing))}" if missing else ""),
                ast_matrix._start,
                ast_matrix._end,
            )
        matrices.append({k: await v.eval(EMPTY_ROOT) for k, v in inc_spec.items()})
    return matrices


async def setup_cache(
    ctx: RootABC,
    base_cache: CacheConf,
    ast_cache: Optional[ast.Cache],
    default_strategy: ast.CacheStrategy,
) -> CacheConf:
    if ast_cache is None:
        return base_cache

    strategy = ast_cache.strategy
    if strategy is None:
        strategy = default_strategy
    if strategy == ast.CacheStrategy.INHERIT:
        strategy = base_cache.strategy

    life_span = await ast_cache.life_span.eval(ctx)
    if life_span is None:
        life_span = base_cache.life_span
    else:
        life_span = min(base_cache.life_span, life_span)
    return CacheConf(strategy=strategy, life_span=life_span)


class RunningLiveFlow:
    _ast_flow: ast.LiveFlow
    _ctx: LiveContext
    _cl: ConfigLoader

    def __init__(
        self,
        ast_flow: ast.LiveFlow,
        ctx: LiveContext,
        config_loader: ConfigLoader,
        defaults: DefaultsConf,
    ):
        self._ast_flow = ast_flow
        self._ctx = ctx
        self._cl = config_loader
        self._defaults = defaults

    @property
    def job_ids(self) -> Iterable[str]:
        return sorted(self._ast_flow.jobs)

    @property
    def flow(self) -> FlowCtx:
        return self._ctx.flow

    @property
    def tags(self) -> AbstractSet[str]:
        return self._ctx.tags

    @property
    def volumes(self) -> Mapping[str, VolumeCtx]:
        return self._ctx.volumes

    @property
    def images(self) -> Mapping[str, ImageCtx]:
        return self._ctx.images

    async def is_multi(self, job_id: str) -> bool:
        # Simple shortcut
        return (await self.get_meta(job_id)).multi

    def _get_job_ast(self, job_id: str) -> Union[ast.Job, ast.JobActionCall]:
        try:
            return self._ast_flow.jobs[job_id]
        except KeyError:
            raise UnknownJob(job_id)

    async def _get_action_ast(self, call_ast: ast.JobActionCall) -> ast.LiveAction:
        action_name = await call_ast.action.eval(EMPTY_ROOT)
        action_ast = await self._cl.fetch_action(action_name)
        if action_ast.kind != ast.ActionKind.LIVE:
            raise TypeError(
                f"Invalid action '{action_ast}' "
                f"type {action_ast.kind.value} for live flow"
            )
        assert isinstance(action_ast, ast.LiveAction)
        return action_ast

    async def get_meta(self, job_id: str) -> JobMeta:
        job_ast = self._get_job_ast(job_id)

        if isinstance(job_ast, ast.JobActionCall):
            action_ast = await self._get_action_ast(job_ast)
            multi = await action_ast.job.multi.eval(EMPTY_ROOT)
        else:
            multi = await job_ast.multi.eval(EMPTY_ROOT)

        tags = set(self.tags)
        tags.add(f"job:{_id2tag(job_id)}")
        return JobMeta(
            id=job_id,
            multi=bool(multi),
            tags=tags,
        )

    async def get_job(self, job_id: str, params: Mapping[str, str]) -> Job:
        assert not await self.is_multi(
            job_id
        ), "Use get_multi_job() for multi jobs instead of get_job()"
        job_ast = self._get_job_ast(job_id)
        ctx = self._ctx.to_job_ctx(
            params=await setup_params_ctx(EMPTY_ROOT, params, job_ast.params)
        )
        return await self._get_job(ctx, ctx.env, self._defaults, job_id)

    async def get_multi_job(
        self,
        job_id: str,
        suffix: str,
        args: Optional[Sequence[str]],
        params: Mapping[str, str],
    ) -> Job:
        assert await self.is_multi(
            job_id
        ), "Use get_job() for not multi jobs instead of get_multi_job()"

        if args is None:
            args_str = ""
        else:
            args_str = " ".join(shlex.quote(arg) for arg in args)
        job_ast = self._get_job_ast(job_id)
        ctx = self._ctx.to_multi_job_ctx(
            multi=MultiCtx(suffix=suffix, args=args_str),
            params=await setup_params_ctx(EMPTY_ROOT, params, job_ast.params),
        )
        job = await self._get_job(ctx, ctx.env, self._defaults, job_id)
        return replace(job, tags=job.tags | {f"multi:{suffix}"})

    async def _get_job(
        self,
        ctx: RootABC,
        env_ctx: EnvCtx,
        defaults: DefaultsConf,
        job_id: str,
    ) -> Job:
        job = self._get_job_ast(job_id)
        if isinstance(job, ast.JobActionCall):
            action_ast = await self._get_action_ast(job)
            ctx = LiveActionContext(
                inputs=await setup_inputs_ctx(ctx, job, action_ast.inputs),
                _client=self._ctx._client,
            )
            env_ctx = {}
            defaults = DefaultsConf()
            job = action_ast.job
        assert isinstance(job, ast.Job)

        tags = (await self.get_meta(job_id)).tags
        if job.tags is not None:
            tmp_tags = await job.tags.eval(ctx)
            assert isinstance(tmp_tags, list)
            tags |= set(tmp_tags)

        env = dict(env_ctx)
        if job.env is not None:
            tmp_env = await job.env.eval(ctx)
            assert isinstance(tmp_env, dict)
            env.update(tmp_env)

        title = await job.title.eval(ctx)
        if title is None:
            title = f"{self._ctx.flow.flow_id}.{job_id}"

        workdir = (await job.workdir.eval(ctx)) or defaults.workdir

        volumes: List[str] = list(defaults.volumes)
        if job.volumes is not None:
            tmp_volumes = await job.volumes.eval(ctx)
            assert isinstance(tmp_volumes, list)
            for volume in tmp_volumes:
                if volume:
                    volumes.append(volume)

        life_span = (await job.life_span.eval(ctx)) or defaults.life_span

        preset = (await job.preset.eval(ctx)) or defaults.preset
        schedule_timeout = (
            await job.schedule_timeout.eval(ctx)
        ) or defaults.schedule_timeout
        port_forward: List[str] = []
        if job.port_forward is not None:
            tmp_port_forward = await job.port_forward.eval(ctx)
            assert isinstance(tmp_port_forward, list)
            port_forward = tmp_port_forward

        return Job(
            id=job_id,
            detach=bool(await job.detach.eval(ctx)),
            browse=bool(await job.browse.eval(ctx)),
            title=title,
            name=await job.name.eval(ctx),
            image=await job.image.eval(ctx),
            preset=preset,
            schedule_timeout=schedule_timeout,
            entrypoint=await job.entrypoint.eval(ctx),
            cmd=await job.cmd.eval(ctx),
            workdir=workdir,
            volumes=volumes,
            life_span=life_span,
            http_port=await job.http_port.eval(ctx),
            http_auth=await job.http_auth.eval(ctx),
            pass_config=await job.pass_config.eval(ctx),
            port_forward=port_forward,
            multi=await self.is_multi(job_id),
            env=env,
            tags=tags,
        )

    @classmethod
    async def create(
        cls, config_loader: ConfigLoader, config_name: str = "live"
    ) -> "RunningLiveFlow":
        ast_flow = await config_loader.fetch_flow(config_name)

        assert isinstance(ast_flow, ast.LiveFlow)

        flow_ctx = await setup_flow_ctx(
            EMPTY_ROOT, ast_flow, config_name, config_loader
        )

        step_1_ctx = LiveContextStep1(flow=flow_ctx, _client=config_loader.client)

        defaults, env, tags = await setup_defaults_env_tags_ctx(
            step_1_ctx, ast_flow.defaults
        )

        live_ctx = step_1_ctx.to_live_ctx(
            env=env,
            tags=tags,
            volumes=await setup_volumes_ctx(step_1_ctx, ast_flow.volumes),
            images=await setup_images_ctx(step_1_ctx, ast_flow.images),
        )

        return cls(ast_flow, live_ctx, config_loader, defaults)


_T = TypeVar("_T", bound=BaseBatchContext, covariant=True)


class EarlyBatch:
    def __init__(
        self, tasks: Mapping[str, "BaseEarlyTask"], config_loader: ConfigLoader
    ):
        self._cl = config_loader
        self._tasks = tasks

    @property
    def graph(self) -> Mapping[str, Mapping[str, ast.NeedsLevel]]:
        return self._graph()

    @lru_cache()
    def _graph(self) -> Mapping[str, Mapping[str, ast.NeedsLevel]]:
        # This function is only needed for mypy
        return {key: early_task.needs for key, early_task in self._tasks.items()}

    def _get_prep(self, real_id: str) -> "BaseEarlyTask":
        try:
            return self._tasks[real_id]
        except KeyError:
            raise UnknownTask(real_id)

    async def is_task(self, real_id: str) -> bool:
        early_task = self._get_prep(real_id)
        return isinstance(early_task, EarlyTask)

    async def is_local(self, real_id: str) -> bool:
        early_task = self._get_prep(real_id)
        return isinstance(early_task, EarlyLocalCall)

    async def is_action(self, real_id: str) -> bool:
        early_task = self._get_prep(real_id)
        return isinstance(early_task, EarlyBatchCall)

    async def state_from(self, real_id: str) -> Optional[str]:
        prep_task = self._get_prep(real_id)
        if isinstance(prep_task, EarlyPostTask):
            return prep_task.state_from
        return None

    def _task_context_class(self) -> Type[Context]:
        return BatchTaskContext

    def _known_inputs(self) -> AbstractSet[str]:
        return set()

    def validate_expressions(self) -> List[EvalError]:
        from .expr_validation import validate_expr

        errors: List[EvalError] = []
        for task in self._tasks.values():
            ctx_cls = self._task_context_class()
            known_needs = task.needs.keys()
            known_inputs = self._known_inputs()
            errors += validate_expr(task.enable, ctx_cls, known_needs, known_inputs)
            if isinstance(task, EarlyTask):
                _ctx_cls = ctx_cls
                if isinstance(task, EarlyStatefulCall):
                    _ctx_cls = StatefulActionContext
                    known_inputs = (task.action.inputs or {}).keys()
                ast_task = task.ast_task
                for field in fields(ast.ExecUnit):
                    field_value = getattr(ast_task, field.name)
                    if field_value is not None and isinstance(field_value, Expr):
                        errors += validate_expr(
                            field_value, _ctx_cls, known_needs, known_inputs
                        )
            if isinstance(task, BaseEarlyCall):
                args = task.call.args or {}
                for arg_expr in args.values():
                    errors += validate_expr(
                        arg_expr, ctx_cls, known_needs, known_inputs
                    )
            if isinstance(task, EarlyLocalCall):
                known_inputs = (task.action.inputs or {}).keys()
                errors += validate_expr(
                    task.action.cmd, LocalActionContext, known_inputs=known_inputs
                )
        return errors

    async def get_action_early(self, real_id: str) -> "EarlyBatch":
        assert await self.is_action(
            real_id
        ), f"get_action_early() cannot used for action call {real_id}"
        prep_task = self._get_prep(real_id)
        assert isinstance(prep_task, EarlyBatchCall)  # Already checked

        await validate_action_call(prep_task.call, prep_task.action.inputs)
        tasks = await EarlyTaskGraphBuilder(self._cl, prep_task.action.tasks).build()

        return EarlyBatchAction(tasks, self._cl, prep_task.action)

    async def get_local_early(self, real_id: str) -> "EarlyLocalCall":
        assert await self.is_local(
            real_id
        ), f"get_local_early() cannot used for action call {real_id}"
        prep_task = self._get_prep(real_id)
        assert isinstance(prep_task, EarlyLocalCall)  # Already checked
        return prep_task


class EarlyBatchAction(EarlyBatch):
    def __init__(
        self,
        tasks: Mapping[str, "BaseEarlyTask"],
        config_loader: ConfigLoader,
        action: ast.BatchAction,
    ):
        super().__init__(tasks, config_loader)
        self._action = action

    def _task_context_class(self) -> Type[Context]:
        return BatchActionTaskContext

    def _known_inputs(self) -> AbstractSet[str]:
        return (self._action.inputs or {}).keys()

    def validate_expressions(self) -> List[EvalError]:
        from .expr_validation import validate_expr

        errors = super().validate_expressions()
        known_inputs = self._known_inputs()

        if self._action.cache:
            errors += validate_expr(
                self._action.cache.life_span,
                BatchActionContext,
                known_inputs=known_inputs,
            )
        outputs = self._action.outputs

        tasks_ids = self._tasks.keys()
        if outputs and outputs.values:
            for output in outputs.values.values():
                errors += validate_expr(
                    output.value,
                    BatchActionOutputsContext,
                    known_needs=tasks_ids,
                    known_inputs=known_inputs,
                )
        return errors


class RunningBatchBase(Generic[_T], EarlyBatch):
    _tasks: Mapping[str, "BasePrepTask"]

    def __init__(
        self,
        ctx: _T,
        default_tags: TagsCtx,
        tasks: Mapping[str, "BasePrepTask"],
        config_loader: ConfigLoader,
        defaults: DefaultsConf,
        bake_id: str,
    ):
        super().__init__(tasks, config_loader)
        self._ctx = ctx
        self._default_tags = default_tags
        self._bake_id = bake_id
        self._defaults = defaults

    def _get_prep(self, real_id: str) -> "BasePrepTask":
        prep_task = super()._get_prep(real_id)
        assert isinstance(prep_task, BasePrepTask)
        return prep_task

    def _task_context(
        self, real_id: str, needs: NeedsCtx, state: StateCtx
    ) -> BaseTaskContext:
        prep_task = self._get_prep(real_id)
        needs_completed = {
            task_id
            for task_id, level in prep_task.needs.items()
            if level == ast.NeedsLevel.COMPLETED
        }
        if needs.keys() != needs_completed:
            extra = ",".join(needs.keys() - needs_completed)
            missing = ",".join(needs_completed - needs.keys())
            err = ["Error in 'needs':"]
            if extra:
                err.append(f"unexpected keys {extra}")
            if missing:
                err.append(f"missing keys {missing}")
            raise ValueError(" ".join(err))
        return self._ctx.to_matrix_ctx(
            matrix=prep_task.matrix,
            strategy=prep_task.strategy,
        ).to_task_ctx(
            needs=needs,
            state=state,
        )

    async def get_meta(
        self, real_id: str, needs: NeedsCtx, state: StateCtx
    ) -> TaskMeta:
        prep_task = self._get_prep(real_id)
        ctx = self._task_context(real_id, needs, state)
        return TaskMeta(
            enable=await prep_task.enable.eval(ctx),
            strategy=prep_task.strategy,
            cache=prep_task.cache,
        )

    async def get_task(
        self, prefix: FullID, real_id: str, needs: NeedsCtx, state: StateCtx
    ) -> Task:
        assert await self.is_task(
            real_id
        ), f"get_task() cannot be used for tasks action call with id {real_id}"
        prep_task = self._get_prep(real_id)
        assert isinstance(prep_task, (PrepTask, PrepStatefulCall))  # Already checked

        task_ctx = self._task_context(real_id, needs, state)
        ctx: RootABC = task_ctx
        defaults = self._defaults

        if isinstance(prep_task, PrepStatefulCall):
            ctx = StatefulActionContext(
                inputs=await setup_inputs_ctx(
                    ctx, prep_task.call, prep_task.action.inputs
                ),
                _client=self._ctx._client,
            )
            defaults = DefaultsConf()  # TODO: Is it correct?

        full_id = prefix + (real_id,)

        if isinstance(ctx, BatchTaskContext):
            env = dict(ctx.env)
        else:
            env = {}

        if prep_task.ast_task.env is not None:
            tmp_env = await prep_task.ast_task.env.eval(ctx)
            assert isinstance(tmp_env, dict)
            env.update(tmp_env)

        title = await prep_task.ast_task.title.eval(ctx)

        tags = set()
        if prep_task.ast_task.tags is not None:
            tmp_tags = await prep_task.ast_task.tags.eval(ctx)
            assert isinstance(tmp_tags, list)
            tags |= set(tmp_tags)

        tags |= {"task:" + _id2tag(".".join(full_id))}
        tags |= set(self._default_tags)

        workdir = (await prep_task.ast_task.workdir.eval(ctx)) or defaults.workdir

        volumes: List[str] = list(defaults.volumes)
        if prep_task.ast_task.volumes is not None:
            tmp_volumes = await prep_task.ast_task.volumes.eval(ctx)
            assert isinstance(tmp_volumes, list)
            for val in tmp_volumes:
                if val:
                    volumes.append(val)

        life_span = (await prep_task.ast_task.life_span.eval(ctx)) or defaults.life_span

        preset = (await prep_task.ast_task.preset.eval(ctx)) or defaults.preset
        schedule_timeout = (
            await prep_task.ast_task.schedule_timeout.eval(ctx)
        ) or defaults.schedule_timeout
        # Enable should be calculated using outer ctx for stateful calls
        enable = (await self.get_meta(real_id, needs, state)).enable

        task = Task(
            id=prep_task.id,
            title=title,
            name=(await prep_task.ast_task.name.eval(ctx)),
            image=await prep_task.ast_task.image.eval(ctx),
            preset=preset,
            schedule_timeout=schedule_timeout,
            entrypoint=await prep_task.ast_task.entrypoint.eval(ctx),
            cmd=await prep_task.ast_task.cmd.eval(ctx),
            workdir=workdir,
            volumes=volumes,
            life_span=life_span,
            http_port=await prep_task.ast_task.http_port.eval(ctx),
            http_auth=await prep_task.ast_task.http_auth.eval(ctx),
            pass_config=await prep_task.ast_task.pass_config.eval(ctx),
            enable=enable,
            cache=prep_task.cache,
            strategy=prep_task.strategy,
            tags=tags,
            env=env,
            caching_key="",
        )
        return replace(
            task,
            tags=task.tags | {f"bake_id:{self._bake_id}"},
            caching_key=_hash(dict(task=task, ctx=ctx)),
        )

    async def get_action(
        self, real_id: str, needs: NeedsCtx
    ) -> "RunningBatchActionFlow":
        assert await self.is_action(
            real_id
        ), f"get_task() cannot used for action call {real_id}"
        prep_task = self._get_prep(real_id)
        assert isinstance(prep_task, PrepBatchCall)  # Already checked

        ctx = self._task_context(real_id, needs, {})

        return await RunningBatchActionFlow.create(
            action_name=prep_task.action_name,
            ast_action=prep_task.action,
            base_cache=prep_task.cache,
            base_strategy=prep_task.strategy,
            inputs=await setup_inputs_ctx(ctx, prep_task.call, prep_task.action.inputs),
            default_tags=self._default_tags,
            bake_id=self._bake_id,
            config_loader=self._cl,
        )

    async def get_local(self, real_id: str, needs: NeedsCtx) -> LocalTask:
        assert await self.is_local(
            real_id
        ), f"get_task() cannot used for action call {real_id}"
        prep_task = self._get_prep(real_id)
        assert isinstance(prep_task, PrepLocalCall)  # Already checked

        ctx = self._task_context(real_id, needs, {})

        action_ctx = LocalActionContext(
            inputs=await setup_inputs_ctx(ctx, prep_task.call, prep_task.action.inputs),
            _client=self._ctx._client,
        )

        return LocalTask(
            id=prep_task.id,
            cmd=await prep_task.action.cmd.eval(action_ctx),
        )


class RunningBatchFlow(RunningBatchBase[BatchContext]):
    def __init__(
        self,
        ctx: BatchContext,
        tasks: Mapping[str, "BasePrepTask"],
        config_loader: ConfigLoader,
        defaults: DefaultsConf,
        bake_id: str,
    ):
        super().__init__(ctx, ctx.tags, tasks, config_loader, defaults, bake_id)

    @property
    def project_id(self) -> str:
        return self._ctx.flow.project_id

    @property
    def volumes(self) -> Mapping[str, VolumeCtx]:
        return self._ctx.volumes

    @property
    def images(self) -> Mapping[str, ImageCtx]:
        return self._ctx.images

    @property
    def life_span(self) -> Optional[timedelta]:
        if self._ctx.flow.life_span:
            return timedelta(seconds=self._ctx.flow.life_span)
        return None

    @property
    def workspace(self) -> LocalPath:
        return self._ctx.flow.workspace

    @classmethod
    async def create(
        cls,
        config_loader: ConfigLoader,
        batch: str,
        bake_id: str,
        params: Optional[Mapping[str, str]] = None,
    ) -> "RunningBatchFlow":
        ast_flow = await config_loader.fetch_flow(batch)

        assert isinstance(ast_flow, ast.BatchFlow)

        flow_ctx = await setup_batch_flow_ctx(
            EMPTY_ROOT, ast_flow, batch, config_loader
        )
        params_ctx = await setup_params_ctx(EMPTY_ROOT, params, ast_flow.params)
        step_1_ctx = BatchContextStep1(
            flow=flow_ctx,
            params=params_ctx,
            _client=config_loader.client,
        )

        defaults, env, tags = await setup_defaults_env_tags_ctx(
            step_1_ctx, ast_flow.defaults
        )

        step_2_ctx = step_1_ctx.to_step_2(
            env=env,
            tags=tags,
            volumes=await setup_volumes_ctx(step_1_ctx, ast_flow.volumes),
            images=await setup_images_ctx(step_1_ctx, ast_flow.images),
        )

        if ast_flow.defaults:
            ast_cache = ast_flow.defaults.cache
        else:
            ast_cache = None
        cache_conf = await setup_cache(
            step_2_ctx, CacheConf(), ast_cache, ast.CacheStrategy.INHERIT
        )

        batch_ctx = step_2_ctx.to_batch_ctx(
            strategy=await setup_strategy_ctx(step_2_ctx, ast_flow.defaults),
        )

        tasks = await TaskGraphBuilder(
            batch_ctx, config_loader, cache_conf, ast_flow.tasks
        ).build()

        return RunningBatchFlow(batch_ctx, tasks, config_loader, defaults, bake_id)


EarlyBatchAction


class RunningBatchActionFlow(RunningBatchBase[BatchActionContext]):
    def __init__(
        self,
        ctx: BatchActionContext,
        default_tags: TagsCtx,
        tasks: Mapping[str, "BasePrepTask"],
        config_loader: ConfigLoader,
        defaults: DefaultsConf,
        action: ast.BatchAction,
        bake_id: str,
    ):
        super().__init__(ctx, default_tags, tasks, config_loader, defaults, bake_id)
        self._action = action

    async def calc_outputs(self, task_results: NeedsCtx) -> DepCtx:
        if any(i.result == TaskStatus.FAILED for i in task_results.values()):
            return DepCtx(TaskStatus.FAILED, {})
        elif any(i.result == TaskStatus.CANCELLED for i in task_results.values()):
            return DepCtx(TaskStatus.CANCELLED, {})
        else:
            ctx = self._ctx.to_outputs_ctx(task_results)
            ret = {}
            if self._action.outputs and self._action.outputs.values is not None:
                for name, descr in self._action.outputs.values.items():
                    val = await descr.value.eval(ctx)
                    assert val is not None
                    ret[name] = val
            return DepCtx(TaskStatus.SUCCEEDED, ret)

    @classmethod
    async def create(
        cls,
        action_name: str,
        ast_action: ast.BatchAction,
        base_cache: CacheConf,
        base_strategy: StrategyCtx,
        inputs: InputsCtx,
        default_tags: TagsCtx,
        config_loader: ConfigLoader,
        bake_id: str,
    ) -> "RunningBatchActionFlow":
        action_context = BatchActionContext(
            inputs=inputs,
            strategy=base_strategy,
            _client=config_loader.client,
        )

        cache = await setup_cache(
            action_context, base_cache, ast_action.cache, ast.CacheStrategy.INHERIT
        )

        tasks = await TaskGraphBuilder(
            action_context, config_loader, cache, ast_action.tasks
        ).build()

        return RunningBatchActionFlow(
            action_context,
            default_tags,
            tasks,
            config_loader,
            DefaultsConf(),
            ast_action,
            bake_id,
        )


# Task graph builder


@dataclass(frozen=True)
class BaseEarlyTask:
    id: Optional[str]
    real_id: str
    needs: Mapping[str, ast.NeedsLevel]  # Keys are batch.id

    matrix: MatrixCtx
    enable: EnableExpr

    def to_task(self, ast_task: ast.ExecUnit) -> "EarlyTask":
        return EarlyTask(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            enable=self.enable,
            ast_task=ast_task,
        )

    def to_batch_call(
        self,
        action_name: str,
        action: ast.BatchAction,
        call: ast.TaskActionCall,
    ) -> "EarlyBatchCall":
        return EarlyBatchCall(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            enable=self.enable,
            action_name=action_name,
            action=action,
            call=call,
        )

    def to_local_call(
        self,
        action_name: str,
        action: ast.LocalAction,
        call: ast.TaskActionCall,
    ) -> "EarlyLocalCall":
        return EarlyLocalCall(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            enable=self.enable,
            action_name=action_name,
            action=action,
            call=call,
        )

    def to_stateful_call(
        self,
        action_name: str,
        action: ast.StatefulAction,
        call: ast.TaskActionCall,
    ) -> "EarlyStatefulCall":
        return EarlyStatefulCall(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            ast_task=action.main,
            enable=self.enable,
            action_name=action_name,
            action=action,
            call=call,
        )

    def to_post_task(self, ast_task: ast.ExecUnit, state_from: str) -> "EarlyPostTask":
        return EarlyPostTask(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            enable=self.enable,
            ast_task=ast_task,
            state_from=state_from,
        )

    def to_prep_base(self, strategy: StrategyCtx, cache: CacheConf) -> "BasePrepTask":
        return BasePrepTask(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            enable=self.enable,
            strategy=strategy,
            cache=cache,
        )


@dataclass(frozen=True)
class EarlyTask(BaseEarlyTask):
    ast_task: ast.ExecUnit


@dataclass(frozen=True)
class BaseEarlyCall(BaseEarlyTask):
    call: ast.TaskActionCall
    action_name: str


@dataclass(frozen=True)
class EarlyBatchCall(BaseEarlyCall):
    action: ast.BatchAction


@dataclass(frozen=True)
class EarlyLocalCall(BaseEarlyCall):
    action: ast.LocalAction


@dataclass(frozen=True)
class EarlyStatefulCall(EarlyTask, BaseEarlyCall):
    action: ast.StatefulAction


@dataclass(frozen=True)
class EarlyPostTask(EarlyTask):
    state_from: str


@dataclass(frozen=True)
class BasePrepTask(BaseEarlyTask):
    strategy: StrategyCtx
    cache: CacheConf

    def to_task(self, ast_task: ast.ExecUnit) -> "PrepTask":
        return PrepTask(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            strategy=self.strategy,
            cache=self.cache,
            enable=self.enable,
            ast_task=ast_task,
        )

    def to_batch_call(
        self,
        action_name: str,
        action: ast.BatchAction,
        call: ast.TaskActionCall,
    ) -> "PrepBatchCall":
        return PrepBatchCall(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            strategy=self.strategy,
            cache=self.cache,
            enable=self.enable,
            action_name=action_name,
            action=action,
            call=call,
        )

    def to_local_call(
        self,
        action_name: str,
        action: ast.LocalAction,
        call: ast.TaskActionCall,
    ) -> "PrepLocalCall":
        return PrepLocalCall(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            strategy=self.strategy,
            cache=CacheConf(strategy=ast.CacheStrategy.NONE),
            enable=self.enable,
            action_name=action_name,
            action=action,
            call=call,
        )

    def to_stateful_call(
        self,
        action_name: str,
        action: ast.StatefulAction,
        call: ast.TaskActionCall,
    ) -> "PrepStatefulCall":
        return PrepStatefulCall(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            strategy=self.strategy,
            cache=CacheConf(strategy=ast.CacheStrategy.NONE),
            enable=self.enable,
            action_name=action_name,
            ast_task=action.main,
            action=action,
            call=call,
        )

    def to_post_task(self, ast_task: ast.ExecUnit, state_from: str) -> "PrepPostTask":
        return PrepPostTask(
            id=self.id,
            real_id=self.real_id,
            needs=self.needs,
            matrix=self.matrix,
            strategy=self.strategy,
            cache=CacheConf(strategy=ast.CacheStrategy.NONE),
            enable=self.enable,
            ast_task=ast_task,
            state_from=state_from,
        )


@dataclass(frozen=True)
class PrepTask(EarlyTask, BasePrepTask):
    pass


@dataclass(frozen=True)
class PrepBatchCall(EarlyBatchCall, BasePrepTask):
    pass


@dataclass(frozen=True)
class PrepLocalCall(EarlyLocalCall, BasePrepTask):
    pass


@dataclass(frozen=True)
class PrepStatefulCall(EarlyStatefulCall, PrepTask):
    pass


@dataclass(frozen=True)
class PrepPostTask(EarlyPostTask, PrepTask):
    pass


class EarlyTaskGraphBuilder:
    MATRIX_SIZE_LIMIT = 256

    def __init__(
        self,
        config_loader: ConfigLoader,
        ast_tasks: Sequence[Union[ast.Task, ast.TaskActionCall]],
    ):
        self._cl = config_loader
        self._ast_tasks = ast_tasks

    async def _extend_base(
        self, base: BaseEarlyTask, ast_task: Union[ast.Task, ast.TaskActionCall]
    ) -> BaseEarlyTask:
        return base

    async def build(self) -> Mapping[str, BaseEarlyTask]:
        post_tasks: List[List[EarlyPostTask]] = []
        prep_tasks: Dict[str, BaseEarlyTask] = {}
        last_needs: Set[str] = set()

        # Only used for sanity checks
        real_id_to_need_to_expr: Dict[str, Mapping[str, IdExpr]] = {}

        for num, ast_task in enumerate(self._ast_tasks, 1):
            assert isinstance(ast_task, (ast.Task, ast.TaskActionCall))

            matrix_ast = ast_task.strategy.matrix if ast_task.strategy else None
            matrices = await setup_matrix(matrix_ast)

            if len(matrices) > self.MATRIX_SIZE_LIMIT:
                assert matrix_ast
                raise EvalError(
                    f"The matrix size for task #{num} exceeds the limit of 256",
                    matrix_ast._start,
                    matrix_ast._end,
                )

            real_ids = set()
            post_tasks_group = []
            for matrix in matrices:
                # make prep patch(es)
                matrix_ctx = MatrixOnlyContext(
                    matrix=matrix,
                    _client=self._cl.client,
                )

                task_id, real_id = await self._setup_ids(matrix_ctx, num, ast_task)
                needs, need_to_expr = await self._setup_needs(
                    matrix_ctx, last_needs, ast_task
                )
                real_id_to_need_to_expr[real_id] = need_to_expr

                base = BaseEarlyTask(
                    id=task_id,
                    real_id=real_id,
                    needs=needs,
                    matrix=matrix,
                    enable=ast_task.enable,
                )
                base = await self._extend_base(base, ast_task)

                if isinstance(ast_task, ast.Task):
                    prep_tasks[real_id] = base.to_task(ast_task)
                else:
                    assert isinstance(ast_task, ast.TaskActionCall)
                    action_name = await ast_task.action.eval(EMPTY_ROOT)
                    action = await self._cl.fetch_action(action_name)
                    if ast_task.cache and not isinstance(action, ast.BatchAction):
                        raise EvalError(
                            f"Specifying cache in action call to the action "
                            f"{action_name} of kind {action.kind.value} is "
                            f"not supported.",
                            ast_task._start,
                            ast_task._end,
                        )
                    if isinstance(action, ast.BatchAction):
                        prep_tasks[real_id] = base.to_batch_call(
                            action_name, action, ast_task
                        )
                    elif isinstance(action, ast.LocalAction):
                        prep_tasks[real_id] = base.to_local_call(
                            action_name, action, ast_task
                        )
                    elif isinstance(action, ast.StatefulAction):
                        if action.post:
                            post_tasks_group.append(
                                replace(
                                    base,
                                    id=None,
                                    real_id=f"post-{base.real_id}",
                                    needs={real_id: ast.NeedsLevel.COMPLETED},
                                    enable=action.post_if,
                                ).to_post_task(action.post, real_id),
                            )
                        prep_tasks[real_id] = base.to_stateful_call(
                            action_name, action, ast_task
                        )

                    else:
                        raise ValueError(
                            f"Action {action_name} has kind {action.kind.value}, "
                            "that is not supported in batch mode."
                        )
                real_ids.add(real_id)

            if post_tasks_group:
                post_tasks.append(post_tasks_group)

            last_needs = real_ids

        for post_tasks_group in reversed(post_tasks):
            real_ids = set()
            for task in post_tasks_group:
                needs = {need: ast.NeedsLevel.COMPLETED for need in last_needs}
                needs = {**needs, **task.needs}
                task = replace(task, needs=needs)
                prep_tasks[task.real_id] = task
                real_ids.add(task.real_id)
            last_needs = real_ids

        # Check needs sanity
        for prep_task in prep_tasks.values():
            for need_id in prep_task.needs.keys():
                if need_id not in prep_tasks:
                    id_expr = real_id_to_need_to_expr[prep_task.real_id][need_id]
                    raise EvalError(
                        f"Task {prep_task.real_id} needs unknown task {need_id}",
                        id_expr.start,
                        id_expr.end,
                    )
        return prep_tasks

    async def _setup_ids(
        self, ctx: MatrixOnlyContext, num: int, ast_task: ast.TaskBase
    ) -> Tuple[Optional[str], str]:
        task_id = await ast_task.id.eval(ctx)
        if task_id is None:
            # Dash is not allowed in identifier, so the generated read id
            # never clamps with user_provided one.
            suffix = [str(ctx.matrix[k]) for k in sorted(ctx.matrix)]
            real_id = "-".join(["task", str(num), *suffix])
        else:
            real_id = task_id
        return task_id, real_id

    async def _setup_needs(
        self, ctx: RootABC, default_needs: AbstractSet[str], ast_task: ast.TaskBase
    ) -> Tuple[Mapping[str, ast.NeedsLevel], Mapping[str, IdExpr]]:
        if ast_task.needs is not None:
            needs, to_expr_map = {}, {}
            for need, level in ast_task.needs.items():
                need_id = await need.eval(ctx)
                needs[need_id] = level
                to_expr_map[need_id] = need
            return needs, to_expr_map
        return {need: ast.NeedsLevel.COMPLETED for need in default_needs}, {}


class TaskGraphBuilder(EarlyTaskGraphBuilder):
    MATRIX_SIZE_LIMIT = 256

    def __init__(
        self,
        ctx: BaseBatchContext,
        config_loader: ConfigLoader,
        default_cache: CacheConf,
        ast_tasks: Sequence[Union[ast.Task, ast.TaskActionCall]],
    ):
        super().__init__(config_loader, ast_tasks)
        self._ctx = ctx
        self._default_cache = default_cache

    async def _extend_base(
        self, base: BaseEarlyTask, ast_task: Union[ast.Task, ast.TaskActionCall]
    ) -> BasePrepTask:
        strategy = await self._setup_strategy(ast_task.strategy)

        matrix_ctx = self._ctx.to_matrix_ctx(matrix=base.matrix, strategy=strategy)
        cache = await setup_cache(
            matrix_ctx,
            self._default_cache,
            ast_task.cache,
            ast.CacheStrategy.INHERIT,
        )

        return base.to_prep_base(strategy, cache)

    async def build(self) -> Mapping[str, BasePrepTask]:
        # Super method already returns proper type (thanks to _extend_base),
        # but it is hard to properly annotate, so we have to do runtime check here
        ret = {}
        tasks = await super().build()
        for key, value in tasks.items():
            assert isinstance(value, BasePrepTask)
            ret[key] = value
        return ret

    async def _setup_strategy(
        self, ast_strategy: Optional[ast.Strategy]
    ) -> StrategyCtx:
        if ast_strategy is None:
            return self._ctx.strategy

        fail_fast = await ast_strategy.fail_fast.eval(self._ctx)
        if fail_fast is None:
            fail_fast = self._ctx.strategy.fail_fast
        max_parallel = await ast_strategy.max_parallel.eval(self._ctx)
        if max_parallel is None:
            max_parallel = self._ctx.strategy.max_parallel

        return StrategyCtx(fail_fast=fail_fast, max_parallel=max_parallel)


# Utils


def _id2tag(id: str) -> str:
    return id.replace("_", "-").lower()


def _hash(val: Any) -> str:
    hasher = hashlib.new("sha256")
    data = json.dumps(val, sort_keys=True, default=_ctx_default)
    hasher.update(data.encode("utf-8"))
    return hasher.hexdigest()


def _ctx_default(val: Any) -> Any:
    if dataclasses.is_dataclass(val):
        if hasattr(val, "_client"):
            val = dataclasses.replace(val, _client=None)
        ret = dataclasses.asdict(val)
        ret.pop("_client", None)
        return ret
    elif isinstance(val, enum.Enum):
        return val.value
    elif isinstance(val, RemotePath):
        return str(val)
    elif isinstance(val, LocalPath):
        return str(val)
    elif isinstance(val, collections.abc.Set):
        return sorted(val)
    elif isinstance(val, AlwaysT):
        return str(val)
    elif isinstance(val, URL):
        return str(val)
    else:
        raise TypeError(f"Cannot dump {val!r}")
