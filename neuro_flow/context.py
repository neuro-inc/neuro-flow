# Contexts
from dataclasses import dataclass, field, replace

import itertools
import shlex
from typing import (
    AbstractSet,
    ClassVar,
    Dict,
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
from yarl import URL

from . import ast
from .config_loader import ConfigLoader
from .expr import EnableExpr, EvalError, LiteralT, RootABC, StrExpr, TypeT
from .types import AlwaysT, FullID, LocalPath, RemotePath, TaskStatus


# Neuro-flow contexts (variables available during expressions calculation).

# The basic design idea is: we should avoid nested contexts if possible.
#
# That's why there is `env` context but defaults.env and job.env are absent.
#
# During the calculation the `env` context is updated to reflect global envs and job's
# env accordingly. This design principle makes expressions shorter in yaml file.  Short
# expressions are super important since the expression syntax has no user-defined
# variables.


# neuro -- global settings cluster, user, api entrypoint)

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

# strategy -- Enables access to the configured strategy parameters.
#
# Strategy parameters include fail-fast and max-parallel.

# matrix -- Enables access to the matrix parameters you configured for the current job.

# needs -- Enables access to the outputs of all jobs that are defined as a dependency of
# the current job.

# images -- Enables access to image specifications.

# volumes -- Enables access to volume specifications.


class NotAvailable(LookupError):
    def __init__(self, ctx_name: str) -> None:
        super().__init__(f"The '{ctx_name}' context is not available")


class UnknownJob(KeyError):
    pass


class UnknownTask(KeyError):
    pass


@dataclass(frozen=True)
class Neuro:
    pass


@dataclass(frozen=True)
class DepCtx:
    result: TaskStatus
    outputs: Mapping[str, str]


NeedsCtx = Mapping[str, DepCtx]

StateCtx = Mapping[str, str]


MatrixCtx = Mapping[str, LiteralT]


@dataclass(frozen=True)
class StrategyCtx:
    fail_fast: bool = True
    max_parallel: int = 10


@dataclass(frozen=True)
class CacheCtx:
    strategy: ast.CacheStrategy = ast.CacheStrategy.DEFAULT
    life_span: float = 14 * 24 * 3600


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
    life_span: Optional[float]


@dataclass(frozen=True)
class JobCtx(ExecUnitCtx):
    id: str
    detach: bool
    browse: bool
    port_forward: Sequence[str]
    multi: bool


@dataclass(frozen=True)
class MultiCtx:
    args: str
    suffix: str


@dataclass(frozen=True)
class JobMetaCtx:
    # Metadata used for jobs lookup
    id: str
    multi: bool


@dataclass(frozen=True)
class BasePrepTaskCtx:
    id: Optional[str]
    real_id: str

    needs: AbstractSet[str]  # A set of batch.id
    matrix: MatrixCtx
    strategy: StrategyCtx
    enable: EnableExpr
    cache: CacheCtx


@dataclass(frozen=True)
class PrepTaskCtx(BasePrepTaskCtx):
    ast: ast.ExecUnit


@dataclass(frozen=True)
class PrepBatchCallCtx(BasePrepTaskCtx):
    action: str
    args: Mapping[str, StrExpr]


@dataclass(frozen=True)
class PrepLocalCtx(BasePrepTaskCtx):
    action: str
    args: Mapping[str, StrExpr]


@dataclass(frozen=True)
class PrepStatefulCallCtx(PrepTaskCtx):
    action: str
    args: Mapping[str, StrExpr]


@dataclass(frozen=True)
class PrepPostTaskCtx(PrepTaskCtx):
    state_from: str


@dataclass(frozen=True)
class TaskCtx(ExecUnitCtx):
    # executed task
    id: Optional[str]
    full_id: FullID

    needs: AbstractSet[str]  # A set of batch.id

    # continue_on_error: OptBoolExpr
    enable: Union[bool, AlwaysT]


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


@dataclass(frozen=True)
class DefaultsCtx:
    workdir: Optional[RemotePath] = None
    life_span: Optional[float] = None
    preset: Optional[str] = None


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

        click.secho(
            "flow.id attribute is deprecated, use flow.flow_id instead",
            fg="yellow",
        )
        return self.flow_id


_CtxT = TypeVar("_CtxT", bound="BaseContext")


class EmptyRoot(RootABC):
    def lookup(self, name: str) -> TypeT:
        raise NotAvailable(name)


EMPTY_ROOT = EmptyRoot()


@dataclass(frozen=True)
class BaseContext(RootABC):
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False,
        default=(
            "env",
            "tags",
        ),
    )

    _config_loader: ConfigLoader
    _env: Optional[Mapping[str, str]] = None
    _tags: Optional[AbstractSet[str]] = None
    _defaults: Optional[DefaultsCtx] = None

    @property
    def env(self) -> Mapping[str, str]:
        if self._env is None:
            raise NotAvailable("env")
        return self._env

    @property
    def tags(self) -> AbstractSet[str]:
        if self._tags is None:
            raise NotAvailable("tags")
        return self._tags

    @property
    def defaults(self) -> DefaultsCtx:
        if self._defaults is None:
            raise NotAvailable("defaults")
        return self._defaults

    def lookup(self, name: str) -> TypeT:
        if name not in self.LOOKUP_KEYS:
            raise NotAvailable(name)
        ret = getattr(self, name)
        # assert isinstance(ret, (ContainerT, SequenceT, MappingT)), ret
        return cast(TypeT, ret)

    async def fetch_action(self, action_name: str) -> ast.BaseAction:
        return await self._config_loader.fetch_action(action_name)


@dataclass(frozen=True)
class BaseFlowContext(BaseContext):
    FLOW_TYPE: ClassVar[Type[ast.BaseFlow]] = field(init=False)
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False,
        default=BaseContext.LOOKUP_KEYS
        + (
            "flow",
            "volumes",
            "images",
        ),
    )

    _ast_flow: Optional[ast.BaseFlow] = None
    _flow: Optional[FlowCtx] = None

    _images: Optional[Mapping[str, ImageCtx]] = None
    _volumes: Optional[Mapping[str, VolumeCtx]] = None

    @classmethod
    async def create(
        cls: Type[_CtxT],
        config_loader: ConfigLoader,
        config_name: str,
    ) -> _CtxT:
        ast_flow = await config_loader.fetch_flow(config_name)
        assert issubclass(cls, BaseFlowContext)
        assert isinstance(ast_flow, cls.FLOW_TYPE)
        flow_id = await ast_flow.id.eval(EMPTY_ROOT)
        if flow_id is None:
            flow_id = config_name.replace("-", "_")

        project = await config_loader.fetch_project()
        project_id = await project.id.eval(EMPTY_ROOT)
        flow_title = await ast_flow.title.eval(EMPTY_ROOT)

        flow = FlowCtx(
            flow_id=flow_id,
            project_id=project_id,
            workspace=config_loader.workspace,
            title=flow_title or flow_id,
        )

        ctx = cls(
            _ast_flow=ast_flow,
            _flow=flow,
            _config_loader=config_loader,
        )
        ctx = await ctx._with_args()

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

        tags.add(f"project:{_id2tag(project_id)}")
        tags.add(f"flow:{_id2tag(flow_id)}")

        defaults = DefaultsCtx(
            workdir=workdir,
            life_span=life_span,
            preset=preset,
        )
        ctx = replace(ctx, _defaults=defaults, _env=env, _tags=tags)

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

                image_env = {}
                if i.env is not None:
                    image_env.update({k: await v.eval(ctx) for k, v in i.env.items()})

                image_volumes = []
                if i.volumes is not None:
                    for vol in i.volumes:
                        value = await vol.eval(ctx)
                        if value:
                            image_volumes.append(value)

                images[k] = ImageCtx(
                    id=k,
                    ref=await i.ref.eval(ctx),
                    context=context_path,
                    full_context_path=calc_full_path(ctx, context_path),
                    dockerfile=dockerfile_path,
                    full_dockerfile_path=calc_full_path(ctx, dockerfile_path),
                    build_args=build_args,
                    env=image_env,
                    volumes=image_volumes,
                )
        return cast(
            _CtxT,
            replace(
                ctx,
                _volumes=volumes,
                _images=images,
            ),
        )

    @property
    def flow(self) -> FlowCtx:
        if self._flow is None:
            raise NotAvailable("flow")
        return self._flow

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

    async def _with_args(self: _CtxT) -> _CtxT:
        # Calculate batch args context early, no-op for live mode
        return self


@dataclass(frozen=True)
class LiveContext(BaseFlowContext):
    FLOW_TYPE: ClassVar[Type[ast.LiveFlow]] = field(init=False, default=ast.LiveFlow)
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False, default=BaseFlowContext.LOOKUP_KEYS + ("multi", "meta")
    )
    _job: Optional[JobCtx] = None
    _meta: Optional[JobMetaCtx] = None
    _multi: Optional[MultiCtx] = None

    @property
    def job(self) -> JobCtx:
        if self._job is None:
            raise NotAvailable("job")
        return self._job

    @property
    def multi(self) -> MultiCtx:
        if self._multi is None:
            raise NotAvailable("multi")
        return self._multi

    @property
    def meta(self) -> JobMetaCtx:
        if self._meta is None:
            raise NotAvailable("meta")
        return self._meta

    @property
    def job_ids(self) -> List[str]:
        assert isinstance(self._ast_flow, self.FLOW_TYPE)
        return sorted(self._ast_flow.jobs)

    async def is_multi(self, job_id: str) -> bool:
        meta_ctx = await self.with_meta(job_id)
        return meta_ctx.meta.multi

    async def with_multi(
        self, *, suffix: str, args: Optional[Sequence[str]]
    ) -> "LiveContext":
        if self._multi is not None:
            raise TypeError(
                "Cannot enter into the multi context, "
                "if the multi is already initialized"
            )
        assert isinstance(self._ast_flow, self.FLOW_TYPE)
        if args is None:
            args_str = ""
        else:
            args_str = " ".join(shlex.quote(arg) for arg in args)
        return replace(
            self,
            _multi=MultiCtx(suffix=suffix, args=args_str),
        )

    async def with_meta(self, job_id: str) -> "LiveContext":
        if self._meta is not None:
            raise TypeError(
                "Cannot enter into the meta context, "
                "if the meta is already initialized"
            )
        assert isinstance(self._ast_flow, self.FLOW_TYPE)
        try:
            job = self._ast_flow.jobs[job_id]
        except KeyError:
            raise UnknownJob(job_id)

        if isinstance(job, ast.JobActionCall):
            action = await self.fetch_action(await job.action.eval(self))
            if action.kind != ast.ActionKind.LIVE:
                raise TypeError(
                    f"Invalid action '{action}' "
                    f"type {action.kind.value} for live flow"
                )
            assert isinstance(action, ast.LiveAction)
            multi = await action.job.multi.eval(EMPTY_ROOT)
        else:
            assert isinstance(job, ast.Job)
            multi = await job.multi.eval(EMPTY_ROOT)

        tags = set(self.tags)
        tags.add(f"job:{_id2tag(job_id)}")
        return replace(self, _meta=JobMetaCtx(id=job_id, multi=bool(multi)), _tags=tags)

    async def with_job(self, job_id: str) -> "LiveContext":
        if self._job is not None:
            raise TypeError(
                "Cannot enter into the job context, if the job is already initialized"
            )
        assert isinstance(self._ast_flow, self.FLOW_TYPE)

        # Always exists since the meta context is previously creted
        job = self._ast_flow.jobs[job_id]

        if isinstance(job, ast.JobActionCall):
            action_ctx = await LiveActionContext.create(
                (self.flow.flow_id, job_id),  # unused
                await job.action.eval(EMPTY_ROOT),
                self._config_loader,
                self.tags,
            )
            assert isinstance(action_ctx._ast, ast.LiveAction)
            args = {}
            if job.args is not None:
                for k, v in job.args.items():
                    args[k] = await v.eval(self)

            action_ctx = await action_ctx.with_inputs(args)
            assert isinstance(action_ctx._ast, ast.LiveAction)
            assert isinstance(action_ctx._ast.job, ast.Job)
            job_ctx, env, tags = await self._calc_job(
                action_ctx,
                self.flow.flow_id,
                job_id,
                action_ctx._ast.job,
                self.meta.multi,
            )
        else:
            job_ctx, env, tags = await self._calc_job(
                self,
                self.flow.flow_id,
                job_id,
                job,
                self.meta.multi,
            )

        real_tags = self.tags | tags

        if self.meta.multi:
            real_tags |= {f"multi:{self.multi.suffix}"}

        return replace(
            self,
            _job=job_ctx,
            _env=dict(self.env, **env),
            _tags=real_tags,
        )

    @classmethod
    async def _calc_job(
        cls,
        ctx: BaseContext,
        flow_id: str,
        job_id: str,
        job: ast.Job,
        multi: bool,
    ) -> Tuple[JobCtx, Mapping[str, str], AbstractSet[str]]:

        assert isinstance(job, ast.Job)

        tags = set()
        if job.tags is not None:
            tags |= {await v.eval(ctx) for v in job.tags}

        env = {}
        if job.env is not None:
            env.update({k: await v.eval(ctx) for k, v in job.env.items()})

        title = await job.title.eval(ctx)
        if title is None:
            title = f"{flow_id}.{job_id}"

        workdir = (await job.workdir.eval(ctx)) or ctx.defaults.workdir

        volumes = []
        if job.volumes is not None:
            for v in job.volumes:
                val = await v.eval(ctx)
                if val:
                    volumes.append(val)

        life_span = (await job.life_span.eval(ctx)) or ctx.defaults.life_span

        preset = (await job.preset.eval(ctx)) or ctx.defaults.preset
        port_forward = []
        if job.port_forward is not None:
            port_forward = [await val.eval(ctx) for val in job.port_forward]

        job_ctx = JobCtx(
            id=job_id,
            detach=bool(await job.detach.eval(ctx)),
            browse=bool(await job.browse.eval(ctx)),
            title=title,
            name=await job.name.eval(ctx),
            image=await job.image.eval(ctx),
            preset=preset,
            entrypoint=await job.entrypoint.eval(ctx),
            cmd=await job.cmd.eval(ctx),
            workdir=workdir,
            volumes=volumes,
            life_span=life_span,
            http_port=await job.http_port.eval(ctx),
            http_auth=await job.http_auth.eval(ctx),
            port_forward=port_forward,
            multi=multi,
        )
        return job_ctx, env, tags


@dataclass(frozen=True)
class TaskContext(BaseContext):
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False,
        default=BaseContext.LOOKUP_KEYS + ("needs", "state", "matrix", "strategy"),
    )

    _task: Optional[TaskCtx] = None
    _needs: Optional[NeedsCtx] = None
    _state: Optional[StateCtx] = None
    _prep_tasks: Optional[Mapping[str, BasePrepTaskCtx]] = None
    _matrix: Optional[MatrixCtx] = None
    _strategy: Optional[StrategyCtx] = None
    _prefix: FullID = ()
    _graph: Optional[Mapping[str, AbstractSet[str]]] = None
    _cache: Optional[CacheCtx] = None

    async def _prepare(
        self, tasks: Sequence[Union[ast.Task, ast.TaskActionCall]]
    ) -> Dict[str, BasePrepTaskCtx]:
        post_tasks: List[List[BasePrepTaskCtx]] = []
        prep_tasks: Dict[str, BasePrepTaskCtx] = {}
        last_needs: Set[str] = set()
        for num, ast_task in enumerate(tasks, 1):
            assert isinstance(ast_task, (ast.Task, ast.TaskActionCall))

            # eval matrix
            matrix: Sequence[MatrixCtx]
            strategy: StrategyCtx
            default_strategy = self.strategy
            if ast_task.strategy is not None:
                fail_fast = await ast_task.strategy.fail_fast.eval(self)
                if fail_fast is None:
                    fail_fast = default_strategy.fail_fast
                max_parallel = await ast_task.strategy.max_parallel.eval(self)
                if max_parallel is None:
                    max_parallel = default_strategy.max_parallel
                strategy = StrategyCtx(fail_fast=fail_fast, max_parallel=max_parallel)
                if ast_task.strategy.matrix is not None:
                    matrix = await self._build_matrix(ast_task.strategy)
                    matrix = await self._exclude(ast_task.strategy, matrix)
                    matrix = await self._include(ast_task.strategy, matrix)

                    if len(matrix) > 256:
                        raise EvalError(
                            f"The matrix size for task #{num} exceeds the limit of 256",
                            ast_task.strategy.matrix._start,
                            ast_task.strategy.matrix._end,
                        )
                else:
                    matrix = [{}]  # dummy
            else:
                strategy = default_strategy  # default
                matrix = [{}]  # dummy
            real_ids = set()
            post_tasks_group: List[BasePrepTaskCtx] = []
            for row in matrix:
                # make prep patch(es)
                matrix_ctx = await self.with_matrix(strategy, row)
                task_id = await ast_task.id.eval(matrix_ctx)
                if task_id is None:
                    # Dash is not allowed in identifier, so the generated read id
                    # never clamps with user_provided one.
                    suffix = [str(row[k]) for k in sorted(row)]
                    real_id = "-".join(["task", str(num), *suffix])
                else:
                    real_id = task_id
                if real_id in prep_tasks:
                    raise ValueError(f"Duplicated task id {real_id}")
                if ast_task.needs is not None:
                    needs = {await need.eval(matrix_ctx) for need in ast_task.needs}
                else:
                    needs = last_needs

                cache = await self._build_cache(
                    ast_task.cache, ast.CacheStrategy.INHERIT
                )

                if isinstance(ast_task, ast.Task):
                    prep_task = PrepTaskCtx(
                        id=task_id,
                        real_id=real_id,
                        needs=needs,
                        matrix=row,
                        strategy=strategy,
                        cache=cache,
                        enable=ast_task.enable,
                        ast=ast_task,
                    )
                    prep_tasks[real_id] = prep_task
                else:
                    assert isinstance(ast_task, ast.TaskActionCall)
                    action_name = await ast_task.action.eval(EMPTY_ROOT)
                    action = await self.fetch_action(action_name)
                    if isinstance(action, ast.BatchAction):
                        prep_call = PrepBatchCallCtx(
                            id=task_id,
                            real_id=real_id,
                            needs=needs,
                            matrix=row,
                            strategy=strategy,
                            cache=cache,
                            enable=ast_task.enable,
                            action=action_name,
                            args=ast_task.args or {},
                        )
                        prep_tasks[real_id] = prep_call
                    elif isinstance(action, ast.LocalAction):
                        prep_local = PrepLocalCtx(
                            id=task_id,
                            real_id=real_id,
                            needs=needs,
                            matrix=row,
                            strategy=strategy,
                            cache=cache,
                            enable=ast_task.enable,
                            action=action_name,
                            args=ast_task.args or {},
                        )
                        prep_tasks[real_id] = prep_local
                    elif isinstance(action, ast.StatefulAction):
                        main_task = PrepStatefulCallCtx(
                            id=task_id,
                            real_id=real_id,
                            needs=needs,
                            matrix=row,
                            strategy=strategy,
                            cache=cache,
                            enable=ast_task.enable,
                            ast=action.main,
                            action=action_name,
                            args=ast_task.args or {},
                        )
                        prep_tasks[real_id] = main_task
                        if action.post:
                            post_tasks_group.append(
                                PrepPostTaskCtx(
                                    id=None,
                                    real_id=f"post-{real_id}",
                                    needs={real_id},
                                    matrix=row,
                                    strategy=strategy,
                                    cache=cache,
                                    enable=action.post_if,
                                    ast=action.post,
                                    state_from=real_id,
                                )
                            )
                    else:
                        raise ValueError(
                            f"Action {action_name} has kind {action.kind}, "
                            "that is not supported in batch mode."
                        )
                real_ids.add(real_id)

            if post_tasks_group:
                post_tasks.append(post_tasks_group)

            last_needs = real_ids

        for post_tasks_group in reversed(post_tasks):
            real_ids = set()
            for task in post_tasks_group:
                task = replace(task, needs=last_needs | task.needs)
                prep_tasks[task.real_id] = task
                real_ids.add(task.real_id)
            last_needs = real_ids

        return prep_tasks

    @property
    def prefix(self) -> FullID:
        return self._prefix

    @property
    def cache(self) -> CacheCtx:
        if self._cache is None:
            raise NotAvailable("cache")
        return self._cache

    @property
    def task(self) -> TaskCtx:
        if self._task is None:
            raise NotAvailable("task")
        return self._task

    @property
    def needs(self) -> NeedsCtx:
        if self._needs is None:
            raise NotAvailable("needs")
        return self._needs

    @property
    def state(self) -> StateCtx:
        if self._state is None:
            raise NotAvailable("needs")
        return self._state

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
    def graph(self) -> Mapping[str, AbstractSet[str]]:
        # Dependency graph for the context's tasks
        assert self._prep_tasks is not None
        if self._graph is None:
            ret = {}
            for key, val in self._prep_tasks.items():
                ret[key] = val.needs
            # Use the hack with direct setattr
            # to cheat the frozen dataclass write protection
            object.__setattr__(self, "_graph", ret)
        assert self._graph is not None
        return self._graph

    def get_dep_ids(self, real_id: str) -> AbstractSet[str]:
        assert self._prep_tasks is not None
        prep_task = self._prep_tasks[real_id]
        return prep_task.needs

    async def with_matrix(
        self: _CtxT, strategy: StrategyCtx, matrix: MatrixCtx
    ) -> _CtxT:
        assert isinstance(self, TaskContext)
        if self._matrix is not None:
            raise TypeError(
                "Cannot enter into the matrix context if "
                "the matrix is already initialized"
            )
        return cast(_CtxT, replace(self, _strategy=strategy, _matrix=matrix))

    async def is_local(self, real_id: str) -> bool:
        assert self._prep_tasks is not None
        try:
            prep_task = self._prep_tasks[real_id]
            return isinstance(prep_task, PrepLocalCtx)
        except KeyError:
            raise UnknownTask(real_id)

    async def is_action(self, real_id: str) -> bool:
        assert self._prep_tasks is not None
        try:
            prep_task = self._prep_tasks[real_id]
            return isinstance(prep_task, PrepBatchCallCtx)
        except KeyError:
            raise UnknownTask(real_id)

    async def is_enabled(
        self, real_id: str, *, needs: NeedsCtx
    ) -> Union[bool, AlwaysT]:
        assert self._prep_tasks is not None
        assert self._task is None
        try:
            prep_task = self._prep_tasks[real_id]
        except KeyError:
            raise UnknownTask(real_id)
        ctx = await self.with_matrix(prep_task.strategy, prep_task.matrix)
        ctx = replace(ctx, _needs=needs)
        return await prep_task.enable.eval(ctx)

    async def state_from(self, real_id: str) -> Optional[FullID]:
        assert self._prep_tasks is not None
        assert self._task is None
        try:
            prep_task = self._prep_tasks[real_id]
            if isinstance(prep_task, PrepPostTaskCtx):
                return self._prefix + (prep_task.state_from,)
            return None
        except KeyError:
            raise UnknownTask(real_id)

    def _with_task_pre(self, real_id: str, *, needs: NeedsCtx) -> BasePrepTaskCtx:
        assert isinstance(self, TaskContext)
        assert self._prep_tasks is not None
        assert self._prefix is not None

        if self._task is not None:
            raise TypeError(
                "Cannot enter into the task context if "
                "the task is already initialized"
            )
        try:
            prep_task = self._prep_tasks[real_id]
        except KeyError:
            raise UnknownTask(real_id)

        if needs.keys() != prep_task.needs:
            extra = ",".join(needs.keys() - prep_task.needs)
            missing = ",".join(prep_task.needs - needs.keys())
            err = ["Error in 'needs':"]
            if extra:
                err.append(f"unexpected keys {extra}")
            if missing:
                err.append(f"missing keys {missing}")
            raise ValueError(" ".join(err))
        return prep_task

    async def with_action(
        self: _CtxT, real_id: str, *, needs: NeedsCtx
    ) -> "BatchActionContext":
        # real_id -- the task's real id
        #
        # outputs -- real_id -> (output_name -> value) mapping for all task ids
        # enumerated in needs.
        #
        # TODO: multi-state tasks require 'state' mapping (state_name -> value)
        assert isinstance(self, TaskContext)
        assert self._prep_tasks is not None
        prep_task = self._with_task_pre(real_id, needs=needs)

        if isinstance(prep_task, PrepTaskCtx):
            raise RuntimeError("Use .with_task() for calling an task-typed task")

        assert isinstance(prep_task, PrepBatchCallCtx)
        action = await self.fetch_action(prep_task.action)
        if action.kind != ast.ActionKind.BATCH:
            raise TypeError(
                f"Invalid action '{action}' " f"type {action.kind.value} for batch flow"
            )
        parent_ctx = await self.with_matrix(prep_task.strategy, prep_task.matrix)
        full_id = self._prefix + (prep_task.real_id,)
        ctx = await BatchActionContext.create(
            full_id,
            prep_task.action,
            self._config_loader,
            parent_ctx.tags,
            {k: await v.eval(parent_ctx) for k, v in prep_task.args.items()},
            parent_ctx.strategy,
            prep_task.cache,
        )
        return ctx

    async def with_local(
        self: _CtxT, real_id: str, *, needs: NeedsCtx
    ) -> "LocalActionContext":
        # real_id -- the task's real id
        #
        # outputs -- real_id -> (output_name -> value) mapping for all task ids
        # enumerated in needs.
        #
        # TODO: multi-state tasks require 'state' mapping (state_name -> value)
        assert isinstance(self, TaskContext)
        assert self._prep_tasks is not None
        prep_task = self._with_task_pre(real_id, needs=needs)

        if not isinstance(prep_task, PrepLocalCtx):
            raise RuntimeError(
                "Use .with_action() or .with_task() for calling non local task"
            )

        assert isinstance(prep_task, PrepLocalCtx), prep_task
        ctx = await self.with_matrix(prep_task.strategy, prep_task.matrix)
        ctx = replace(ctx, _needs=needs, _cache=prep_task.cache)

        action_ctx = await LocalActionContext.create(
            self._prefix + (prep_task.real_id,),  # unused
            prep_task.action,
            self._config_loader,
            self.tags,
        )
        action_ctx = await action_ctx.with_inputs(
            {k: await v.eval(ctx) for k, v in prep_task.args.items()}
        )
        return await action_ctx.with_cmd()

    async def with_task(
        self: _CtxT, real_id: str, *, needs: NeedsCtx, state: Optional[StateCtx]
    ) -> _CtxT:
        # real_id -- the task's real id
        #
        # outputs -- real_id -> (output_name -> value) mapping for all task ids
        # enumerated in needs.
        #
        # TODO: multi-state tasks require 'state' mapping (state_name -> value)
        assert isinstance(self, TaskContext)
        assert self._prep_tasks is not None
        prep_task = self._with_task_pre(real_id, needs=needs)

        if isinstance(prep_task, PrepBatchCallCtx):
            raise RuntimeError("Use .with_action() for calling an action-typed task")

        assert isinstance(prep_task, PrepTaskCtx), prep_task
        task_ctx_base = await self.with_matrix(prep_task.strategy, prep_task.matrix)
        task_ctx_base = replace(
            task_ctx_base, _needs=needs, _cache=prep_task.cache, _state=state
        )

        ctx: BaseContext = task_ctx_base

        if isinstance(prep_task, PrepStatefulCallCtx):
            action_ctx = await StatefulActionContext.create(
                self._prefix + (prep_task.real_id,),  # unused
                prep_task.action,
                self._config_loader,
                self.tags,
            )
            ctx = await action_ctx.with_inputs(
                {k: await v.eval(ctx) for k, v in prep_task.args.items()}
            )

            action = await self.fetch_action(prep_task.action)
            assert isinstance(action, ast.StatefulAction)
            task_ctx_base = replace(
                task_ctx_base,
                _cache=await self._build_cache(action.cache, ast.CacheStrategy.INHERIT),
            )

        full_id = self._prefix + (prep_task.real_id,)

        env = dict(ctx.env)
        if prep_task.ast.env is not None:
            env.update({k: await v.eval(ctx) for k, v in prep_task.ast.env.items()})

        title = await prep_task.ast.title.eval(ctx)
        if title is None:
            title = ".".join(full_id)
        title = await prep_task.ast.title.eval(ctx)

        tags = set()
        if prep_task.ast.tags is not None:
            tags = {await v.eval(ctx) for v in prep_task.ast.tags}
        if not tags:
            tags = {"task:" + _id2tag(".".join(full_id))}

        workdir = (await prep_task.ast.workdir.eval(ctx)) or ctx.defaults.workdir

        volumes = []
        if prep_task.ast.volumes is not None:
            for v in prep_task.ast.volumes:
                val = await v.eval(ctx)
                if val:
                    volumes.append(val)

        life_span = (await prep_task.ast.life_span.eval(ctx)) or ctx.defaults.life_span

        preset = (await prep_task.ast.preset.eval(ctx)) or ctx.defaults.preset

        enable = await self.is_enabled(real_id, needs=needs)

        task_ctx = TaskCtx(
            id=prep_task.id,
            full_id=full_id,
            needs=prep_task.needs,
            title=title,
            name=(await prep_task.ast.name.eval(ctx)),
            image=await prep_task.ast.image.eval(ctx),
            preset=preset,
            entrypoint=await prep_task.ast.entrypoint.eval(ctx),
            cmd=await prep_task.ast.cmd.eval(ctx),
            workdir=workdir,
            volumes=volumes,
            life_span=life_span,
            http_port=await prep_task.ast.http_port.eval(ctx),
            http_auth=await prep_task.ast.http_auth.eval(ctx),
            enable=enable,
        )
        return cast(
            _CtxT,
            replace(
                task_ctx_base,
                _task=task_ctx,
                _env=env,
                _tags=ctx.tags | tags,
            ),
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
            include = True
            for exc in exclude:
                match = True
                for k, v in exc.items():
                    if row[k] != v:
                        match = False
                        break
                if match:
                    include = False
                    break
            if include:
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

    async def _build_cache(
        self, ast_cache: Optional[ast.Cache], default: ast.CacheStrategy
    ) -> CacheCtx:
        if ast_cache is None:
            return self.cache
        strategy = ast_cache.strategy
        if strategy is None:
            strategy = default
        if strategy == ast.CacheStrategy.INHERIT:
            strategy = self.cache.strategy
        life_span = await ast_cache.life_span.eval(self)
        if life_span is None:
            life_span = self.cache.life_span
        else:
            life_span = min(self.cache.life_span, life_span)
        return CacheCtx(strategy=strategy, life_span=life_span)


@dataclass(frozen=True)
class BatchContext(TaskContext, BaseFlowContext):
    FLOW_TYPE: ClassVar[Type[ast.BatchFlow]] = field(init=False, default=ast.BatchFlow)
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False,
        default=BaseFlowContext.LOOKUP_KEYS + TaskContext.LOOKUP_KEYS + ("args",),
    )
    _args: Optional[Mapping[str, str]] = None

    @classmethod
    async def create(
        cls: Type[_CtxT],
        config_loader: ConfigLoader,
        config_name: str,
    ) -> _CtxT:
        ctx = await super(cls, BatchContext).create(config_loader, config_name)
        ast_flow = await config_loader.fetch_flow(config_name)
        ast_defaults = ast_flow.defaults
        ctx = replace(ctx, _cache=CacheCtx())
        if ast_defaults is not None:
            assert isinstance(ast_defaults, ast.BatchFlowDefaults), ast_defaults
            fail_fast = await ast_defaults.fail_fast.eval(ctx)
            if fail_fast is None:
                fail_fast = StrategyCtx.fail_fast
            max_parallel = await ast_defaults.max_parallel.eval(ctx)
            if max_parallel is None:
                max_parallel = StrategyCtx.max_parallel
            strategy = StrategyCtx(fail_fast=fail_fast, max_parallel=max_parallel)
            cache = await ctx._build_cache(
                ast_defaults.cache, ast.CacheStrategy.DEFAULT
            )
        else:
            strategy = StrategyCtx()
            cache = ctx.cache

        ctx = replace(ctx, _strategy=strategy, _cache=cache)

        assert issubclass(cls, BatchContext), cls
        assert isinstance(ctx._ast_flow, ast.BatchFlow)

        prep_tasks = await ctx._prepare(ctx._ast_flow.tasks)

        return cast(_CtxT, replace(ctx, _prefix=(), _prep_tasks=prep_tasks))

    async def _with_args(self: _CtxT) -> _CtxT:
        # Calculate batch args context early, no-op for live mode
        assert isinstance(self, BaseFlowContext)
        assert isinstance(self._ast_flow, ast.BatchFlow)
        args = {}
        if self._ast_flow.args is not None:
            for k, v in self._ast_flow.args.items():
                default = await v.default.eval(EMPTY_ROOT)
                # descr = await v.descr.eval(EMPTY_ROOT)
                if default is None:
                    raise EvalError(
                        f"Arg {k} is not initialized and has no default value",
                        v._start,
                        v._end,
                    )
                args[k] = default
        return cast(_CtxT, replace(self, _args=args))

    @property
    def args(self) -> Mapping[str, str]:
        if self._args is None:
            raise NotAvailable("args")
        return self._args


@dataclass(frozen=True)
class ActionContext(BaseContext):
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False,
        default=BaseContext.LOOKUP_KEYS + ("inputs",),
    )

    _ast: Optional[ast.BaseAction] = None
    _action: str = ""

    _inputs: Optional[Mapping[str, str]] = None
    _prefix: FullID = ()
    # Add a context with global flow info, e.g. ctx.flow.id maybe?

    @classmethod
    async def create(
        cls: Type[_CtxT],
        prefix: FullID,
        action: str,
        config_loader: ConfigLoader,
        tags: AbstractSet[str],
    ) -> _CtxT:
        assert issubclass(cls, ActionContext)
        ctx = cls(
            _action=action,
            _config_loader=config_loader,
        )
        ast_action = await ctx.fetch_action(action)
        assert isinstance(ast_action, ast.BaseAction)

        return cast(
            _CtxT,
            replace(
                ctx,
                _prefix=prefix,
                _ast=ast_action,
                _inputs=None,
                _env={},
                _tags=set(tags),
                _defaults=DefaultsCtx(),
            ),
        )

    @property
    def prefix(self) -> FullID:
        return self._prefix

    @property
    def action(self) -> str:
        return self._action

    @property
    def inputs(self) -> Mapping[str, str]:
        if self._inputs is None:
            raise NotAvailable("inputs")
        return self._inputs

    async def with_inputs(self: _CtxT, inputs: Mapping[str, str]) -> _CtxT:
        assert isinstance(self, ActionContext)
        if self._inputs is not None:
            raise TypeError(
                "Cannot enter into the task context if "
                "the task is already initialized"
            )
        assert self._ast is not None
        if self._ast.inputs is None:
            if inputs:
                raise ValueError(f"Unsupported input(s): {','.join(sorted(inputs))}")
            else:
                return cast(_CtxT, self)
        new_inputs = dict(inputs)
        for name, inp in self._ast.inputs.items():
            if name not in new_inputs and inp.default.pattern is not None:
                val = await inp.default.eval(EMPTY_ROOT)
                # inputs doesn't support expressions,
                # non-none pattern means non-none input
                assert val is not None
                new_inputs[name] = val
        extra = new_inputs.keys() - self._ast.inputs.keys()
        if extra:
            raise ValueError(f"Unsupported input(s): {','.join(sorted(extra))}")
        missing = self._ast.inputs.keys() - new_inputs.keys()
        if missing:
            raise ValueError(f"Required input(s): {','.join(sorted(missing))}")
        return cast(_CtxT, replace(self, _inputs=new_inputs))

    def _check_kind(self, required: ast.ActionKind) -> None:
        assert self._ast is not None
        if self._ast.kind != required:
            raise TypeError(
                f"Invalid action '{self._action}' "
                f"type {self._ast.kind.value}, {required.value} is required"
            )


@dataclass(frozen=True)
class LiveActionContext(ActionContext):
    @classmethod
    async def create(
        cls: Type[_CtxT],
        prefix: FullID,
        action: str,
        config_loader: ConfigLoader,
        tags: AbstractSet[str],
    ) -> _CtxT:
        ret = await super(cls, LiveActionContext).create(
            prefix, action, config_loader, tags
        )
        ret._check_kind(ast.ActionKind.LIVE)
        return cast(_CtxT, ret)


@dataclass(frozen=True)
class LocalActionContext(ActionContext):
    _cmd: Optional[str] = None

    @classmethod
    async def create(
        cls: Type[_CtxT],
        prefix: FullID,
        action: str,
        config_loader: ConfigLoader,
        tags: AbstractSet[str],
    ) -> _CtxT:
        ret = await super(cls, LocalActionContext).create(
            prefix, action, config_loader, tags
        )
        ret._check_kind(ast.ActionKind.LOCAL)
        return cast(_CtxT, ret)

    @property
    def cmd(self) -> str:
        assert self._cmd is not None
        return self._cmd

    async def with_cmd(self) -> "LocalActionContext":
        assert isinstance(self._ast, ast.LocalAction)
        shell = await self._ast.cmd.eval(self)
        return replace(self, _cmd=shell)


@dataclass(frozen=True)
class StatefulActionContext(ActionContext):
    @classmethod
    async def create(
        cls: Type[_CtxT],
        prefix: FullID,
        action: str,
        config_loader: ConfigLoader,
        tags: AbstractSet[str],
    ) -> _CtxT:
        ret = await super(cls, StatefulActionContext).create(
            prefix, action, config_loader, tags
        )
        ret._check_kind(ast.ActionKind.STATEFUL)
        return cast(_CtxT, ret)


@dataclass(frozen=True)
class BatchActionContext(TaskContext, ActionContext):
    LOOKUP_KEYS: ClassVar[Tuple[str, ...]] = field(
        init=False,
        default=ActionContext.LOOKUP_KEYS + TaskContext.LOOKUP_KEYS,
    )

    @classmethod
    async def create(  # type:ignore[override]
        cls: Type[_CtxT],
        prefix: FullID,
        action: str,
        config_loader: ConfigLoader,
        tags: AbstractSet[str],
        inputs: Mapping[str, str],
        default_strategy: StrategyCtx,
        default_cache: CacheCtx,
    ) -> _CtxT:
        ctx = await super(cls, BatchActionContext).create(  # type:ignore[call-arg]
            prefix, action, config_loader, tags
        )
        ctx._check_kind(ast.ActionKind.BATCH)
        ctx = await ctx.with_inputs(inputs)
        ctx = replace(ctx, _strategy=default_strategy, _cache=default_cache)
        assert isinstance(ctx._ast, ast.BatchAction)
        cache = await ctx._build_cache(ctx._ast.cache, ast.CacheStrategy.INHERIT)
        ctx = replace(ctx, _cache=cache)

        assert isinstance(ctx, BatchActionContext)
        assert isinstance(ctx._ast, ast.BatchAction)
        prep_tasks = await ctx._prepare(ctx._ast.tasks)

        return cast(_CtxT, replace(ctx, _prefix=prefix, _prep_tasks=prep_tasks))

    async def get_output_needs(self) -> AbstractSet[str]:
        assert isinstance(self._ast, ast.BatchAction)
        if self._ast.outputs:
            return {await need.eval(self) for need in self._ast.outputs.needs}
        return set()

    async def calc_outputs(self, needs: NeedsCtx, *, is_cancelling: bool) -> DepCtx:
        if any(i.result == TaskStatus.FAILED for i in needs.values()):
            return DepCtx(TaskStatus.FAILED, {})
        elif any(i.result == TaskStatus.CANCELLED for i in needs.values()):
            return DepCtx(TaskStatus.CANCELLED, {})
        elif any(i.result == TaskStatus.SKIPPED for i in needs.values()):
            # If some of our needs are disabled, then either
            # action is misconfigured (and so it is failed)
            # or cancellation is in progress.
            # We cannot return DISABLED here, because it means
            # that task did not start at all but this action
            # is in progress when we are here.
            if is_cancelling:
                return DepCtx(TaskStatus.CANCELLED, {})
            else:
                return DepCtx(TaskStatus.FAILED, {})
        else:
            ret = {}
            assert isinstance(self._ast, ast.BatchAction)
            ctx = replace(self, _needs=needs)
            if self._ast.outputs and self._ast.outputs.values is not None:
                for name, descr in self._ast.outputs.values.items():
                    val = await descr.value.eval(ctx)
                    assert val is not None
                    ret[name] = val
            return DepCtx(TaskStatus.SUCCEEDED, ret)


def calc_full_path(
    ctx: BaseFlowContext, path: Optional[LocalPath]
) -> Optional[LocalPath]:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return ctx.flow.workspace.joinpath(path).resolve()


def _id2tag(id: str) -> str:
    return id.replace("_", "-").lower()
