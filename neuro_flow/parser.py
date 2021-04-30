# YAML parser
#
# The parser converts YAML entities into ast data classes.
#
# Defaults are evaluated by the separate processing step.


import dataclasses

import abc
import enum
import logging
import yaml
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Mapping,
    Optional,
    Sequence,
    TextIO,
    Type,
    TypeVar,
    Union,
    cast,
)
from yaml.composer import Composer
from yaml.constructor import ConstructorError, SafeConstructor
from yaml.parser import Parser
from yaml.reader import Reader
from yaml.resolver import Resolver as BaseResolver
from yaml.scanner import Scanner

from . import ast
from .ast import NeedsLevel
from .expr import (
    BaseExpr,
    EnableExpr,
    Expr,
    IdExpr,
    MappingExpr,
    MappingItemsExpr,
    MappingT,
    OptBashExpr,
    OptBoolExpr,
    OptIdExpr,
    OptIntExpr,
    OptLocalPathExpr,
    OptPythonExpr,
    OptRemotePathExpr,
    OptStrExpr,
    OptTimeDeltaExpr,
    PortPairExpr,
    RemotePathExpr,
    SequenceExpr,
    SequenceItemsExpr,
    SequenceT,
    SimpleIdExpr,
    SimpleOptBoolExpr,
    SimpleOptIdExpr,
    SimpleOptStrExpr,
    SimpleStrExpr,
    StrExpr,
    TypeT,
    URIExpr,
    port_pair_item,
)
from .tokenizer import Pos
from .types import LocalPath


log = logging.getLogger(__name__)


_T = TypeVar("_T", bound=TypeT)
_Container = TypeVar("_Container")


@dataclasses.dataclass
class ConfigDir:
    workspace: LocalPath
    config_dir: LocalPath


@dataclasses.dataclass
class ConfigPath:
    workspace: LocalPath
    config_file: LocalPath


class BaseConstructor(SafeConstructor):
    def construct_id(self, node: yaml.Node) -> str:
        val = self.construct_object(node)  # type: ignore[no-untyped-call]
        if not isinstance(val, str):
            raise ConstructorError(
                None, None, f"expected a str, found {type(val)}", node.start_mark
            )
        if not val.isidentifier():
            raise ConstructorError(
                None, None, f"{val} is not an identifier", node.start_mark
            )
        if val == val.upper():
            raise ConstructorError(
                None,
                None,
                f"{val} is invalid identifier, "
                "uppercase names are reserved for internal usage",
                node.start_mark,
            )
        return val


def mark2pos(mark: yaml.Mark) -> Pos:
    return Pos(mark.line, mark.column, LocalPath(mark.name))


class SimpleCompound(Generic[_T, _Container], abc.ABC):
    def __init__(self, factory: Type[Expr[_T]]) -> None:
        self._factory = factory

    @abc.abstractmethod
    def construct(self, ctor: BaseConstructor, node: yaml.Node) -> _Container:
        pass

    def check_scalar(self, ctor: BaseConstructor, node: yaml.Node) -> None:
        node_id = node.id  # type: ignore
        if node_id != "scalar":
            raise ConstructorError(
                None,
                None,
                f"expected a scalar node, but found {node_id}",
                node.start_mark,
            )


class SimpleSeq(SimpleCompound[_T, Sequence[Expr[_T]]]):
    def construct(self, ctor: BaseConstructor, node: yaml.Node) -> Sequence[Expr[_T]]:
        if not isinstance(node, yaml.SequenceNode):
            node_id = node.id  # type: ignore
            raise ConstructorError(
                None,
                None,
                f"expected a sequence node, but found {node_id}",
                node.start_mark,
            )
        ret = []
        for child in node.value:
            self.check_scalar(ctor, child)
            val = ctor.construct_object(child)  # type: ignore[no-untyped-call]
            # check if scalar
            if val is not None:
                val = str(val)
            tmp = self._factory(
                mark2pos(child.start_mark), mark2pos(child.end_mark), val
            )
            ret.append(tmp)
        return ret


class SimpleMapping(SimpleCompound[_T, Mapping[str, Expr[_T]]]):
    def construct(
        self, ctor: BaseConstructor, node: yaml.Node
    ) -> Mapping[str, Expr[_T]]:
        if not isinstance(node, yaml.MappingNode):
            node_id = node.id  # type: ignore
            raise ConstructorError(
                None,
                None,
                f"expected a mapping node, but found {node_id}",
                node.start_mark,
            )
        ret = {}
        for k, v in node.value:
            key = ctor.construct_object(k)  # type: ignore[no-untyped-call]
            self.check_scalar(ctor, v)
            tmp = ctor.construct_object(v)  # type: ignore[no-untyped-call]
            if tmp is not None:
                tmp = str(tmp)
            value = self._factory(mark2pos(v.start_mark), mark2pos(v.end_mark), tmp)
            ret[key] = value
        return ret


class IdMapping(SimpleCompound[_T, Mapping[str, Expr[_T]]]):
    def construct(
        self, ctor: BaseConstructor, node: yaml.Node
    ) -> Mapping[str, Expr[_T]]:
        if not isinstance(node, yaml.MappingNode):
            node_id = node.id  # type: ignore
            raise ConstructorError(
                None,
                None,
                f"expected a mapping node, but found {node_id}",
                node.start_mark,
            )
        ret = {}
        for k, v in node.value:
            key = ctor.construct_id(k)
            self.check_scalar(ctor, v)
            tmp = ctor.construct_object(v)  # type: ignore[no-untyped-call]
            if tmp is not None:
                tmp = str(tmp)
            value = self._factory(mark2pos(v.start_mark), mark2pos(v.end_mark), tmp)
            ret[key] = value
        return ret


class ExprOrSeq(SimpleCompound[_T, BaseExpr[SequenceT]]):
    def __init__(
        self,
        item_expr_factory: Type[Expr[_T]],
        item_value_factory: Callable[[TypeT], TypeT],
    ) -> None:
        super().__init__(item_expr_factory)
        self._item_factory = item_value_factory

    def construct(self, ctor: BaseConstructor, node: yaml.Node) -> BaseExpr[SequenceT]:
        if isinstance(node, yaml.ScalarNode):
            val = ctor.construct_object(node)  # type: ignore[no-untyped-call]
            return SequenceExpr(
                mark2pos(node.start_mark),
                mark2pos(node.end_mark),
                val,
                self._item_factory,
            )
        else:
            seq = SimpleSeq(self._factory).construct(ctor, node)
            return SequenceItemsExpr(seq)


class ExprOrMapping(SimpleCompound[_T, BaseExpr[MappingT]]):
    def __init__(
        self,
        item_expr_factory: Type[Expr[_T]],
        item_value_factory: Callable[[TypeT], TypeT],
    ) -> None:
        super().__init__(item_expr_factory)
        self._item_factory = item_value_factory

    def construct(self, ctor: BaseConstructor, node: yaml.Node) -> BaseExpr[MappingT]:
        if isinstance(node, yaml.ScalarNode):
            val = ctor.construct_object(node)  # type: ignore[no-untyped-call]
            return MappingExpr(
                mark2pos(node.start_mark),
                mark2pos(node.end_mark),
                val,
                self._item_factory,
            )
        else:
            seq = SimpleMapping(self._factory).construct(ctor, node)
            return MappingItemsExpr(seq)


def type2str(arg: TypeT) -> TypeT:
    if arg is None:
        return arg
    return str(arg)


_AstType = TypeVar("_AstType", bound=ast.Base)
_CtorType = TypeVar("_CtorType", bound=BaseConstructor)


def parse_dict(
    ctor: _CtorType,
    node: yaml.MappingNode,
    keys: Mapping[str, Any],
    res_type: Type[_AstType],
    *,
    ret_name: Optional[str] = None,
    extra: Optional[Mapping[str, Union[str, LocalPath]]] = None,
    preprocess: Optional[
        Callable[[_CtorType, yaml.MappingNode, Dict[str, Any]], Dict[str, Any]]
    ] = None,
    find_res_type: Optional[
        Callable[
            [_CtorType, yaml.MappingNode, Type[_AstType], Dict[str, Any]],
            Type[_AstType],
        ]
    ] = None,
) -> _AstType:
    if extra is None:
        extra = {}
    if ret_name is None:
        ret_name = res_type.__name__
    if not isinstance(node, yaml.MappingNode):
        node_id = node.id
        raise ConstructorError(
            None,
            None,
            f"expected a mapping node, but found '{node_id}'",
            node.start_mark,
        )
    node_start = mark2pos(node.start_mark)
    node_end = mark2pos(node.end_mark)

    data = dict(extra)
    for k, v in node.value:
        key = ctor.construct_object(k)  # type: ignore[no-untyped-call]
        if key not in keys:
            raise ConstructorError(
                f"while constructing a '{ret_name}'",
                node.start_mark,
                f"unexpected key '{key}'",
                k.start_mark,
            )
        item_ctor: Any = keys[key]
        tmp: Any
        value: Any
        if item_ctor is None:
            # Get constructor from tag
            value = ctor.construct_object(v)  # type: ignore[no-untyped-call]
        elif isinstance(item_ctor, type) and issubclass(item_ctor, enum.Enum):
            tmp = str(ctor.construct_object(v))  # type: ignore[no-untyped-call]
            value = item_ctor(tmp)
        elif isinstance(item_ctor, ast.Base):
            assert isinstance(
                v, ast.Base
            ), f"[{type(v)}] '{v}' should be ast.Base derived"
            value = v
        elif isinstance(item_ctor, SimpleCompound):
            value = item_ctor.construct(ctor, v)
        elif isinstance(item_ctor, type) and issubclass(item_ctor, Expr):
            tmp = ctor.construct_object(v)  # type: ignore[no-untyped-call]
            value = item_ctor(mark2pos(v.start_mark), mark2pos(v.end_mark), tmp)
        else:
            raise ConstructorError(
                f"while constructing a '{ret_name}'",
                node.start_mark,
                f"unexpected value tag '{v.tag}' for key '{key}[{item_ctor}]'",
                k.start_mark,
            )
        data[key] = value

    if preprocess is not None:
        data = preprocess(ctor, node, dict(data))
    if find_res_type is not None:
        res_type = find_res_type(ctor, node, res_type, dict(data))
        ret_name = res_type.__name__

    optional_fields: Dict[str, Any] = {}
    found_fields = data.keys() | {"_start", "_end"}
    field_names = set()
    for f in dataclasses.fields(res_type):
        field_names.add(f.name)
        if f.name not in found_fields:
            key = f.name
            item_ctor = keys[key]
            if (
                item_ctor is None
                or isinstance(item_ctor, SimpleCompound)
                or isinstance(item_ctor, ast.Base)
            ):
                if f.metadata.get("allow_none", False):
                    optional_fields[f.name] = None
                else:
                    raise ConstructorError(
                        f"while constructing a '{ret_name}', "
                        f"missing mandatory key '{f.name}'",
                        node.start_mark,
                    )
            elif isinstance(item_ctor, type) and issubclass(item_ctor, Expr):
                default_expr = f.metadata.get("default_expr", None)
                if default_expr:
                    fake_node = dataclasses.replace(node_start, line=0, col=0)
                    optional_fields[f.name] = item_ctor(
                        fake_node, fake_node, default_expr
                    )
                elif not item_ctor.allow_none:
                    raise ConstructorError(
                        f"while constructing a '{ret_name}', "
                        f"missing mandatory key '{f.name}'",
                        node.start_mark,
                    )
                else:
                    optional_fields[f.name] = item_ctor(node_start, node_end, None)
            elif isinstance(item_ctor, type) and issubclass(item_ctor, enum.Enum):
                if f.metadata.get("allow_none", False):
                    optional_fields[f.name] = None
            else:
                raise ConstructorError(
                    f"while constructing a '{ret_name}', "
                    f"unexpected '{f.name}' constructor type '{item_ctor!r}'",
                    node.start_mark,
                )

    actual_names = found_fields | optional_fields.keys()
    missing_names = field_names - actual_names
    sep = ","
    if missing_names:
        raise ConstructorError(
            f"while constructing a '{ret_name}', "
            f"missing fields '{sep.join(missing_names)}'",
            node.start_mark,
        )
    unknown_names = actual_names - field_names
    if unknown_names:
        raise ConstructorError(
            f"while constructing a '{ret_name}', "
            f"unexpected fields '{sep.join(missing_names)}'",
            node.start_mark,
        )
    return res_type(  # type: ignore[call-arg]
        _start=node_start,
        _end=node_end,
        **data,
        **optional_fields,
    )


# #### Generics ####


def parse_cache(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Cache:
    return parse_dict(
        ctor,
        node,
        {
            "strategy": ast.CacheStrategy,
            "life_span": OptTimeDeltaExpr,
        },
        ast.Cache,
    )


# #### Project parser ####


class ProjectLoader(Reader, Scanner, Parser, Composer, BaseConstructor, BaseResolver):
    def __init__(self, stream: TextIO) -> None:
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseConstructor.__init__(self)
        BaseResolver.__init__(self)


PROJECT = {"id": SimpleIdExpr}


def parse_project_main(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Project:
    ret = parse_dict(
        ctor,
        node,
        PROJECT,
        ast.Project,
    )
    return ret


ProjectLoader.add_path_resolver("project:main", [])  # type: ignore
ProjectLoader.add_constructor("project:main", parse_project_main)  # type: ignore


def parse_project_stream(stream: TextIO) -> ast.Project:
    ret: ast.Project
    loader = ProjectLoader(stream)
    try:
        ret = loader.get_single_data()  # type: ignore[no-untyped-call]
        assert isinstance(ret, ast.Project)
        return ret
    finally:
        loader.dispose()  # type: ignore[no-untyped-call]


def make_default_project(workspace_stem: str) -> ast.Project:
    project_id = workspace_stem.replace("-", "_")
    if not project_id.isidentifier():
        raise ValueError(
            f'Workspace directory name "{workspace_stem}" is invalid identifier'
        )
    if project_id == project_id.upper():
        raise ValueError(
            f'Workspace directory name "{workspace_stem}" is invalid '
            "identifier, uppercase names are reserved for internal usage"
        )
    return ast.Project(
        _start=Pos(0, 0, LocalPath("<default>")),
        _end=Pos(0, 0, LocalPath("<default>")),
        id=SimpleIdExpr(
            Pos(0, 0, LocalPath("<default>")),
            Pos(0, 0, LocalPath("<default>")),
            project_id,
        ),
    )


# #### Flow parser ####


class FlowLoader(Reader, Scanner, Parser, Composer, BaseConstructor, BaseResolver):
    def __init__(self, stream: TextIO, *, kind: ast.FlowKind) -> None:
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseConstructor.__init__(self)
        BaseResolver.__init__(self)
        self._kind = kind


def parse_volume(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Volume:
    return parse_dict(
        ctor,
        node,
        {
            "remote": URIExpr,
            "mount": RemotePathExpr,
            "read_only": OptBoolExpr,
            "local": OptLocalPathExpr,
        },
        ast.Volume,
    )


def parse_volumes(
    ctor: BaseConstructor, node: yaml.MappingNode
) -> Dict[str, ast.Volume]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_id(k)
        value = parse_volume(ctor, v)
        ret[key] = value
    return ret


FlowLoader.add_path_resolver("flow:volumes", [(dict, "volumes")])  # type: ignore
FlowLoader.add_constructor("flow:volumes", parse_volumes)  # type: ignore


def parse_image(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Image:
    return parse_dict(
        ctor,
        node,
        {
            "ref": StrExpr,
            "context": OptLocalPathExpr,
            "dockerfile": OptLocalPathExpr,
            "build_args": ExprOrSeq(StrExpr, type2str),
            "env": ExprOrMapping(StrExpr, type2str),
            "volumes": ExprOrSeq(OptStrExpr, type2str),
            "build_preset": OptStrExpr,
        },
        ast.Image,
    )


def parse_images(ctor: BaseConstructor, node: yaml.MappingNode) -> Dict[str, ast.Image]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_id(k)
        value = parse_image(ctor, v)
        ret[key] = value
    return ret


FlowLoader.add_path_resolver("flow:images", [(dict, "images")])  # type: ignore
FlowLoader.add_constructor("flow:images", parse_images)  # type: ignore


def parse_needs_key(ctor: BaseConstructor, node: yaml.Node) -> IdExpr:
    tmp = ctor.construct_scalar(node)  # type: ignore[no-untyped-call]
    return IdExpr(mark2pos(node.start_mark), mark2pos(node.end_mark), tmp)


FlowLoader.add_path_resolver(  # type: ignore
    "flow:task_needs_key",
    [(dict, "tasks"), (list, None), (dict, "needs"), (dict, True)],
)
FlowLoader.add_constructor("flow:task_needs_key", parse_needs_key)  # type: ignore


def parse_needs(
    ctor: BaseConstructor, node: yaml.Node
) -> Optional[Mapping[IdExpr, NeedsLevel]]:
    if isinstance(node, yaml.MappingNode):

        def _factory(_start: Pos, _end: Pos, value: Any) -> NeedsLevel:
            return NeedsLevel(value)

        return SimpleMapping(_factory).construct(ctor, node)  # type: ignore
    needs = SimpleSeq(IdExpr).construct(ctor, node)
    return {task_id: NeedsLevel.COMPLETED for task_id in needs}  # type: ignore


FlowLoader.add_path_resolver(  # type: ignore
    "flow:task_needs",
    [(dict, "tasks"), (list, None), (dict, "needs")],
)
FlowLoader.add_constructor("flow:task_needs", parse_needs)  # type: ignore


def parse_exc_inc(
    ctor: BaseConstructor, node: yaml.MappingNode
) -> Sequence[Mapping[str, StrExpr]]:
    if not isinstance(node, yaml.SequenceNode):
        node_id = node.id
        raise ConstructorError(
            None,
            None,
            f"expected a sequence node, but found {node_id}",
            node.start_mark,
        )
    builder = IdMapping(StrExpr)
    ret: List[Mapping[str, StrExpr]] = []
    for v in node.value:
        ret.append(builder.construct(ctor, v))  # type: ignore[arg-type]
    return ret


def parse_matrix(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Matrix:
    if not isinstance(node, yaml.MappingNode):
        node_id = node.id
        raise ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node_id}",
            node.start_mark,
        )
    products_builder = SimpleSeq(StrExpr)
    products = {}
    exclude: Sequence[Mapping[str, StrExpr]] = []
    include: Sequence[Mapping[str, StrExpr]] = []
    for k, v in node.value:
        key = ctor.construct_id(k)
        if key == "include":
            include = parse_exc_inc(ctor, v)
        elif key == "exclude":
            exclude = parse_exc_inc(ctor, v)
        else:
            products[key] = products_builder.construct(ctor, v)
    return ast.Matrix(
        _start=mark2pos(node.start_mark),
        _end=mark2pos(node.end_mark),
        products=products,  # type: ignore[arg-type]
        exclude=exclude,
        include=include,
    )


FlowLoader.add_path_resolver(  # type: ignore
    "flow:matrix",
    [(dict, "tasks"), (list, None), (dict, "strategy"), (dict, "matrix")],
)
FlowLoader.add_constructor("flow:matrix", parse_matrix)  # type: ignore


STRATEGY = {
    "matrix": None,
    "fail_fast": OptBoolExpr,
    "max_parallel": OptIntExpr,
}


def parse_strategy(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Strategy:
    return parse_dict(
        ctor,
        node,
        STRATEGY,
        ast.Strategy,
    )


FlowLoader.add_path_resolver(  # type: ignore
    "flow:strategy", [(dict, "tasks"), (list, None), (dict, "strategy")]
)
FlowLoader.add_constructor("flow:strategy", parse_strategy)  # type: ignore

FlowLoader.add_path_resolver(  # type: ignore
    "flow:cache", [(dict, "tasks"), (list, None), (dict, "cache")]
)
FlowLoader.add_constructor("flow:cache", parse_cache)  # type: ignore

EXEC_UNIT = {
    "title": OptStrExpr,
    "name": OptStrExpr,
    "image": StrExpr,
    "preset": OptStrExpr,
    "schedule_timeout": OptTimeDeltaExpr,
    "entrypoint": OptStrExpr,
    "cmd": OptStrExpr,
    "bash": OptBashExpr,
    "python": OptPythonExpr,
    "workdir": OptRemotePathExpr,
    "env": ExprOrMapping(StrExpr, type2str),
    "volumes": ExprOrSeq(OptStrExpr, type2str),
    "tags": ExprOrSeq(StrExpr, type2str),
    "life_span": OptTimeDeltaExpr,
    "http_port": OptIntExpr,
    "http_auth": OptBoolExpr,
    "pass_config": OptBoolExpr,
}


JOB = {
    "detach": OptBoolExpr,
    "browse": OptBoolExpr,
    "port_forward": ExprOrSeq(PortPairExpr, port_pair_item),
    "multi": SimpleOptBoolExpr,
    "params": None,
    **EXEC_UNIT,
}

JOB_ACTION_CALL = {
    "action": SimpleStrExpr,
    "args": SimpleMapping(StrExpr),
    "params": None,
}


def check_extra(
    node: yaml.Node, dct: Dict[str, Any], ret: Dict[str, Any], name: str
) -> None:
    diff = dct.keys() - ret.keys()
    if diff:
        raise ConstructorError(
            f"{','.join(diff)} are not allowed in {name}", node.start_mark
        )


def select_shells(
    ctor: BaseConstructor, node: yaml.MappingNode, dct: Dict[str, Any]
) -> Dict[str, Any]:
    found = {k for k in dct if k in ("cmd", "bash", "python")}
    if len(found) > 1:
        raise ConstructorError(
            f"{','.join(found)} are mutually exclusive", node.start_mark
        )

    bash = dct.pop("bash", None)
    if bash is not None:
        dct["cmd"] = bash

    python = dct.pop("python", None)
    if python is not None:
        dct["cmd"] = python

    return dct


def select_job_or_action(
    ctor: BaseConstructor, node: yaml.MappingNode, dct: Dict[str, Any]
) -> Dict[str, Any]:
    if "action" in dct:
        ret = {k: v for k, v in dct.items() if k in JOB_ACTION_CALL}
        check_extra(node, dct, ret, "action call")
    else:
        tmp = {k: v for k, v in dct.items() if k in JOB}
        check_extra(node, dct, tmp, "job")
        ret = select_shells(ctor, node, tmp)
    return ret


JOB_OR_ACTION = {**JOB, **JOB_ACTION_CALL}


def find_job_type(
    ctor: BaseConstructor,
    node: yaml.MappingNode,
    res_type: Type[ast.Base],
    arg: Dict[str, Any],
) -> Union[Type[ast.Job], Type[ast.JobActionCall]]:
    action = arg.get("action")
    if action is None:
        return ast.Job
    else:
        return ast.JobActionCall


def parse_job(
    ctor: BaseConstructor, node: yaml.MappingNode
) -> Union[ast.Job, ast.JobActionCall]:
    return cast(
        Union[ast.Job, ast.JobActionCall],
        parse_dict(
            ctor,
            node,
            JOB_OR_ACTION,
            ast.JobBase,
            preprocess=select_job_or_action,
            find_res_type=find_job_type,
        ),
    )


def parse_jobs(
    ctor: BaseConstructor, node: yaml.MappingNode
) -> Dict[str, Union[ast.Job, ast.JobActionCall]]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_id(k)
        value = parse_job(ctor, v)
        ret[key] = value
    return ret


FlowLoader.add_path_resolver("flow:jobs", [(dict, "jobs")])  # type: ignore
FlowLoader.add_constructor("flow:jobs", parse_jobs)  # type: ignore


TASK: Mapping[str, Any] = {
    "id": OptIdExpr,
    "needs": None,
    "strategy": None,
    "enable": EnableExpr,
    "cache": None,
    **EXEC_UNIT,
}


TASK_ACTION_CALL = {
    "id": OptIdExpr,
    "needs": None,
    "strategy": None,
    "enable": EnableExpr,
    "cache": None,
    "action": SimpleStrExpr,
    "args": SimpleMapping(StrExpr),
}


TASK_OR_ACTION = {**TASK, **TASK_ACTION_CALL}


def select_task_or_action(
    ctor: BaseConstructor, node: yaml.MappingNode, dct: Dict[str, Any]
) -> Dict[str, Any]:
    if "action" in dct:
        ret = {k: v for k, v in dct.items() if k in TASK_ACTION_CALL}
        check_extra(node, dct, ret, "action call")
    else:
        tmp = {k: v for k, v in dct.items() if k in TASK}
        check_extra(node, dct, tmp, "task")
        ret = select_shells(ctor, node, tmp)
    return ret


def find_task_type(
    ctor: BaseConstructor,
    node: yaml.MappingNode,
    res_type: Type[ast.Base],
    arg: Dict[str, Any],
) -> Union[Type[ast.Task], Type[ast.TaskActionCall]]:
    action = arg.get("action")
    if action is None:
        return ast.Task
    else:
        return ast.TaskActionCall


def parse_task(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Base:
    return parse_dict(
        ctor,
        node,
        TASK_OR_ACTION,
        ast.Base,
        preprocess=select_task_or_action,
        find_res_type=find_task_type,
    )


FlowLoader.add_path_resolver(  # type: ignore[no-untyped-call]
    "flow:task", [(dict, "tasks"), (list, None)]
)
FlowLoader.add_constructor("flow:task", parse_task)  # type: ignore


FlowLoader.add_path_resolver("flow:tasks", [(dict, "tasks")])  # type: ignore
FlowLoader.add_constructor("flow:tasks", FlowLoader.construct_sequence)  # type: ignore


def parse_flow_defaults(ctor: FlowLoader, node: yaml.MappingNode) -> ast.FlowDefaults:
    if ctor._kind == ast.FlowKind.LIVE:
        return parse_dict(
            ctor,
            node,
            {
                "tags": ExprOrSeq(StrExpr, type2str),
                "env": ExprOrMapping(StrExpr, type2str),
                "volumes": ExprOrSeq(OptStrExpr, type2str),
                "workdir": OptRemotePathExpr,
                "life_span": OptTimeDeltaExpr,
                "preset": OptStrExpr,
                "schedule_timeout": OptTimeDeltaExpr,
            },
            ast.FlowDefaults,
        )
    elif ctor._kind == ast.FlowKind.BATCH:
        return parse_dict(
            ctor,
            node,
            {
                "tags": ExprOrSeq(StrExpr, type2str),
                "env": ExprOrMapping(StrExpr, type2str),
                "volumes": ExprOrSeq(OptStrExpr, type2str),
                "workdir": OptRemotePathExpr,
                "life_span": OptTimeDeltaExpr,
                "preset": OptStrExpr,
                "schedule_timeout": OptTimeDeltaExpr,
                "fail_fast": OptBoolExpr,
                "max_parallel": OptIntExpr,
                "cache": None,
            },
            ast.BatchFlowDefaults,
        )
    else:
        raise ValueError(f"Unknown kind {ctor._kind}")


FlowLoader.add_path_resolver(  # type: ignore
    "flow:cache", [(dict, "defaults"), (dict, "cache")]
)
FlowLoader.add_path_resolver("flow:defaults", [(dict, "defaults")])  # type: ignore
FlowLoader.add_constructor("flow:defaults", parse_flow_defaults)  # type: ignore


FLOW = {
    "kind": ast.FlowKind,
    "id": SimpleOptIdExpr,
    "title": SimpleOptStrExpr,
    "life_span": OptTimeDeltaExpr,
    "images": None,
    "volumes": None,
    "defaults": None,
    "params": None,
    "jobs": None,
    "tasks": None,
}


PARAMS = {"default": SimpleOptStrExpr, "descr": SimpleOptStrExpr}


def parse_param(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Param:
    return parse_dict(ctor, node, PARAMS, ast.Param)


def parse_params(ctor: BaseConstructor, node: yaml.MappingNode) -> Dict[str, ast.Param]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_id(k)
        if isinstance(v, yaml.ScalarNode):
            default = ctor.construct_object(v)  # type: ignore[no-untyped-call]
            start = mark2pos(v.start_mark)
            end = mark2pos(v.end_mark)
            ret[key] = ast.Param(
                _start=start,
                _end=end,
                default=SimpleOptStrExpr(start, end, default),
                descr=SimpleOptStrExpr(start, end, None),
            )
        else:
            arg = parse_param(ctor, v)
            ret[key] = arg
    return ret


FlowLoader.add_path_resolver("flow:params", [(dict, "params")])  # type: ignore
FlowLoader.add_path_resolver(  # type: ignore
    "flow:params",
    [(dict, "jobs"), (dict, None), (dict, "params")],
)
FlowLoader.add_constructor("flow:params", parse_params)  # type: ignore


def find_flow_type(
    ctor: BaseConstructor,
    node: yaml.MappingNode,
    res_type: Type[ast.BaseFlow],
    arg: Dict[str, Any],
) -> Type[ast.BaseFlow]:
    kind = arg.get("kind")
    if kind is None:
        raise ConstructorError(
            f"missing mandatory key 'kind'",
            node.start_mark,
        )

    if kind == ast.FlowKind.LIVE:
        return ast.LiveFlow
    elif kind == ast.FlowKind.BATCH:
        return ast.BatchFlow
    else:
        raise ConstructorError(
            f"unknown kind {kind} of the flow",
            node.start_mark,
        )


def parse_flow_main(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.BaseFlow:
    ret = parse_dict(
        ctor,
        node,
        FLOW,
        ast.BaseFlow,
        find_res_type=find_flow_type,
    )
    return ret


FlowLoader.add_path_resolver("flow:main", [])  # type: ignore
FlowLoader.add_constructor("flow:main", parse_flow_main)  # type: ignore


def parse_live_stream(stream: TextIO) -> ast.LiveFlow:
    loader = FlowLoader(stream, kind=ast.FlowKind.LIVE)
    try:
        ret = loader.get_single_data()  # type: ignore[no-untyped-call]
        assert isinstance(ret, ast.LiveFlow)
        assert ret.kind == ast.FlowKind.LIVE
        return ret
    finally:
        loader.dispose()  # type: ignore[no-untyped-call]


def parse_live(workspace: LocalPath, config_file: LocalPath) -> ast.LiveFlow:
    # Parse live flow config file
    with config_file.open() as f:
        return parse_live_stream(f)


def parse_batch_stream(stream: TextIO) -> ast.BatchFlow:
    loader = FlowLoader(stream, kind=ast.FlowKind.BATCH)
    try:
        ret = loader.get_single_data()  # type: ignore[no-untyped-call]
        assert isinstance(ret, ast.BatchFlow)
        assert ret.kind == ast.FlowKind.BATCH
        return ret
    finally:
        loader.dispose()  # type: ignore[no-untyped-call]


def parse_batch(workspace: LocalPath, config_file: LocalPath) -> ast.BatchFlow:
    # Parse pipeline flow config file
    with config_file.open() as f:
        return parse_batch_stream(f)


def find_workspace(path: Optional[Union[LocalPath, str]]) -> ConfigDir:
    # Find live config file, starting from path.
    # Return a project root folder and a config folder.
    #
    # If path is a not None -- it is used as starting point, LocalPath.cwd() otherwise.
    # The lookup searches bottom-top from path dir up to the root folder,
    # looking for .neuro folder.
    # If the config folder not found -- raise an exception.

    if path is not None:
        if not isinstance(path, LocalPath):
            path = LocalPath(path)
        if not path.exists():
            raise ValueError(f"{path} does not exist")
        if not path.is_dir():
            raise ValueError(f"{path} should be a directory")
    else:
        path = LocalPath.cwd()

    orig_path = path

    while True:
        if path == path.parent:
            raise ValueError(f".neuro folder was not found in lookup for {orig_path}")
        if (path / ".neuro").is_dir():
            break
        path = path.parent

    return ConfigDir(path, path / ".neuro")


# #### Action parser ####


class ActionLoader(Reader, Scanner, Parser, Composer, BaseConstructor, BaseResolver):
    def __init__(self, stream: TextIO) -> None:
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseConstructor.__init__(self)
        BaseResolver.__init__(self)


INPUT = {
    "descr": SimpleOptStrExpr,
    "default": SimpleOptStrExpr,
}


def parse_action_input(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Input:
    ret = parse_dict(
        ctor,
        node,
        INPUT,
        ast.Input,
    )
    return ret


def parse_action_inputs(
    ctor: BaseConstructor, node: yaml.MappingNode
) -> Dict[str, ast.Input]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_id(k)
        value = parse_action_input(ctor, v)
        ret[key] = value
    return ret


ActionLoader.add_path_resolver("action:inputs", [(dict, "inputs")])  # type: ignore
ActionLoader.add_constructor("action:inputs", parse_action_inputs)  # type: ignore

OUTPUT = {
    "descr": SimpleOptStrExpr,
    "value": OptStrExpr,
}


def parse_action_output(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Output:
    ret = parse_dict(
        ctor,
        node,
        OUTPUT,
        ast.Output,
    )
    return ret


@dataclasses.dataclass(frozen=True)
class ParsedActionOutputs(ast.Base):
    # Temporary container. Mapped to real ast in preprocess_action
    needs: Optional[Sequence[IdExpr]]
    values: Optional[Mapping[str, ast.Output]]


def parse_action_outputs(
    ctor: BaseConstructor, node: yaml.MappingNode
) -> ParsedActionOutputs:
    values = {}
    needs = None
    for k, v in node.value:
        key = ctor.construct_id(k)
        if key == "needs" and isinstance(v, yaml.SequenceNode):
            needs = SimpleSeq(IdExpr).construct(ctor, v)
        else:
            value = parse_action_output(ctor, v)
            values[key] = value
    return ParsedActionOutputs(
        _start=mark2pos(node.start_mark),
        _end=mark2pos(node.end_mark),
        needs=needs,  # type: ignore[arg-type]
        values=values,
    )


ActionLoader.add_path_resolver("action:outputs", [(dict, "outputs")])  # type: ignore
ActionLoader.add_constructor("action:outputs", parse_action_outputs)  # type: ignore


def parse_job_in_live_action(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Job:
    ret = parse_job(ctor, node)
    if not isinstance(ret, ast.Job):
        raise ConstructorError(
            f"nested actions are forbidden",
            node.start_mark,
        )
    return ret


ActionLoader.add_path_resolver("action:job", [(dict, "job")])  # type: ignore
ActionLoader.add_constructor("action:job", parse_job_in_live_action)  # type: ignore

ActionLoader.add_path_resolver(  # type: ignore
    "action:matrix",
    [(dict, "tasks"), (list, None), (dict, "strategy"), (dict, "matrix")],
)
ActionLoader.add_constructor("action:matrix", parse_matrix)  # type: ignore

ActionLoader.add_path_resolver(  # type: ignore
    "action:strategy", [(dict, "tasks"), (list, None), (dict, "strategy")]
)
ActionLoader.add_constructor("action:strategy", parse_strategy)  # type: ignore


ActionLoader.add_path_resolver("action:cache", [(dict, "cache")])  # type: ignore
ActionLoader.add_path_resolver(  # type: ignore
    "action:cache", [(dict, "tasks"), (list, None), (dict, "cache")]
)
ActionLoader.add_constructor("action:cache", parse_cache)  # type: ignore


ActionLoader.add_path_resolver(  # type: ignore[no-untyped-call]
    "action:task", [(dict, "tasks"), (list, None)]
)
ActionLoader.add_constructor("action:task", parse_task)  # type: ignore


ActionLoader.add_path_resolver("action:tasks", [(dict, "tasks")])  # type: ignore
ActionLoader.add_constructor(  # type: ignore
    "action:tasks", ActionLoader.construct_sequence
)

ActionLoader.add_path_resolver(  # type: ignore
    "action:task_needs_key",
    [(dict, "tasks"), (list, None), (dict, "needs"), (dict, True)],
)
ActionLoader.add_constructor("action:task_needs_key", parse_needs_key)  # type: ignore
ActionLoader.add_path_resolver(  # type: ignore
    "action:task_needs",
    [(dict, "tasks"), (list, None), (dict, "needs")],
)
ActionLoader.add_constructor("action:task_needs", parse_needs)  # type: ignore


def parse_exec_unit(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.ExecUnit:
    return parse_dict(ctor, node, EXEC_UNIT, ast.ExecUnit, preprocess=select_shells)


ActionLoader.add_path_resolver("action:exec", [(dict, "pre")])  # type: ignore
ActionLoader.add_path_resolver("action:exec", [(dict, "post")])  # type: ignore
ActionLoader.add_path_resolver("action:exec", [(dict, "main")])  # type: ignore
ActionLoader.add_constructor("action:exec", parse_exec_unit)  # type: ignore


BASE_ACTION = {
    "name": SimpleOptStrExpr,
    "author": SimpleOptStrExpr,
    "descr": SimpleOptStrExpr,
    "inputs": None,
    "outputs": None,
    "kind": ast.ActionKind,
}

LIVE_ACTION: Dict[str, Any] = {"job": None, **BASE_ACTION}

BATCH_ACTION: Dict[str, Any] = {"cache": None, "tasks": None, **BASE_ACTION}

STATEFUL_ACTION: Dict[str, Any] = {
    "cache": None,
    "main": None,
    "post": None,
    "post_if": EnableExpr,
    **BASE_ACTION,
}

LOCAL_ACTION: Dict[str, Any] = {
    "cmd": StrExpr,
    **BASE_ACTION,
}

ACTION = {
    **LIVE_ACTION,
    **BATCH_ACTION,
    **STATEFUL_ACTION,
    **LOCAL_ACTION,
}


def _deep_get(node: yaml.Node, path: Sequence[str]) -> Optional[yaml.Node]:
    if not path:
        return node
    if not isinstance(node, yaml.MappingNode):
        return None
    key, *subpath = path
    for k, v in node.value:
        if k.value == key:
            return _deep_get(v, subpath)
    return None


def select_action(
    ctor: BaseConstructor, node: yaml.MappingNode, dct: Dict[str, Any]
) -> Dict[str, Any]:
    kind = dct.get("kind")

    ret: Dict[str, Any]
    if kind == ast.ActionKind.LIVE:
        ret = {k: v for k, v in dct.items() if k in LIVE_ACTION}
    elif kind == ast.ActionKind.BATCH:
        ret = {k: v for k, v in dct.items() if k in BATCH_ACTION}
    elif kind == ast.ActionKind.STATEFUL:
        ret = {k: v for k, v in dct.items() if k in STATEFUL_ACTION}
    elif kind == ast.ActionKind.LOCAL:
        ret = {k: v for k, v in dct.items() if k in LOCAL_ACTION}
    else:
        raise ConstructorError(
            f"missing mandatory key 'kind'",
            node.start_mark,
        )
    check_extra(node, dct, ret, f"{kind.value} action")

    if kind == ast.ActionKind.LIVE:
        if "job" in dct and dct["job"].params is not None:
            raise ConnectionError(
                f"job.params is not supported inside live action, use inputs instead.",
                node.start_mark,
            )

    outputs_tmp: Optional[ParsedActionOutputs] = dct.get("outputs")
    needs_list_node = _deep_get(node, ("outputs", "needs"))

    if outputs_tmp and kind != ast.ActionKind.BATCH:
        if outputs_tmp.needs is not None:
            raise ConnectionError(
                f"outputs.needs list is not supported for {kind.value} action kind",
                (needs_list_node or node).start_mark,
            )
        ret["outputs"] = outputs_tmp.values
    elif outputs_tmp:
        if outputs_tmp.needs is not None:
            log.warning(
                "outputs.needs is deprecated and will have no effect. "
                "All action tasks are available in actions outputs expressions."
                f"\n{(needs_list_node or node).start_mark}"
            )
        ret["outputs"] = ast.BatchActionOutputs(
            _start=outputs_tmp._start,
            _end=outputs_tmp._end,
            values=outputs_tmp.values,
        )
    return ret


def find_action_type(
    ctor: BaseConstructor,
    node: yaml.MappingNode,
    res_type: Type[ast.BaseAction],
    arg: Dict[str, Any],
) -> Type[ast.BaseAction]:
    kind = arg.get("kind")
    if kind is None:
        raise ConstructorError(
            f"missing mandatory key 'kind'",
            node.start_mark,
        )
    ret: Type[ast.BaseAction]
    if kind == ast.ActionKind.LIVE:
        ret = ast.LiveAction
    elif kind == ast.ActionKind.BATCH:
        ret = ast.BatchAction
    elif kind == ast.ActionKind.STATEFUL:
        ret = ast.StatefulAction
    elif kind == ast.ActionKind.LOCAL:
        ret = ast.LocalAction
    else:
        raise ConnectionError(f"unknown kind {kind} of the action", node.start_mark)
    if issubclass(ret, (ast.LiveAction, ast.StatefulAction, ast.LocalAction)):
        for name, val in arg.get("outputs", {}).items():
            if val.value.pattern is not None:
                raise ConnectionError(
                    f"outputs.{name}.value is not supported "
                    f"for {kind.value} action kind",
                    node.start_mark,
                )
    return ret


def parse_action_main(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.BaseAction:
    ret = parse_dict(
        ctor,
        node,
        ACTION,
        ast.BaseAction,
        preprocess=select_action,
        find_res_type=find_action_type,
    )
    return ret


ActionLoader.add_path_resolver("action:main", [])  # type: ignore
ActionLoader.add_constructor("action:main", parse_action_main)  # type: ignore


# #### Action parser ####


class BakeMetaLoader(Reader, Scanner, Parser, Composer, BaseConstructor, BaseResolver):
    def __init__(self, stream: TextIO) -> None:
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseConstructor.__init__(self)
        BaseResolver.__init__(self)


def parse_meta_main(ctor: BaseConstructor, node: yaml.MappingNode) -> Mapping[str, str]:
    if not isinstance(node, yaml.MappingNode):
        raise ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node.id}",
            node.start_mark,
        )
    ret = {}
    for k, v in node.value:
        key = str(ctor.construct_scalar(k))  # type: ignore[no-untyped-call]
        value = str(ctor.construct_scalar(v))  # type: ignore[no-untyped-call]
        ret[key] = value
    return ret


BakeMetaLoader.add_path_resolver("bake_meta:main", [])  # type: ignore
BakeMetaLoader.add_constructor("bake_meta:main", parse_meta_main)  # type: ignore


def parse_action_stream(stream: TextIO) -> ast.BaseAction:
    ret: ast.Project
    loader = ActionLoader(stream)
    try:
        ret = loader.get_single_data()  # type: ignore[no-untyped-call]
        assert isinstance(ret, ast.BaseAction)
        return ret
    finally:
        loader.dispose()  # type: ignore[no-untyped-call]


def parse_action(action_file: LocalPath) -> ast.BaseAction:
    # Parse project config file
    with action_file.open() as f:
        return parse_action_stream(f)


def parse_bake_meta(meta_file: LocalPath) -> Mapping[str, str]:
    with meta_file.open() as f:
        result = BakeMetaLoader(f).get_single_data()  # type: ignore[no-untyped-call]
        assert isinstance(result, dict)
        return result
