# YAML parser
#
# The parser converts YAML entities into ast data classes.
#
# Defaults are evaluated by the separate processing step.


import dataclasses

import abc
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
)
from yaml.composer import Composer
from yaml.constructor import ConstructorError, SafeConstructor
from yaml.parser import Parser
from yaml.reader import Reader
from yaml.resolver import Resolver as BaseResolver
from yaml.scanner import Scanner

from . import ast
from .expr import (
    EvalError,
    Expr,
    IdExpr,
    OptBashExpr,
    OptBoolExpr,
    OptIdExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptLocalPathExpr,
    OptPythonExpr,
    OptRemotePathExpr,
    OptStrExpr,
    PortPairExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)
from .tokenizer import Pos
from .types import LocalPath


_T = TypeVar("_T")
_Cont = TypeVar("_Cont")


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


def parse_bool(ctor: BaseConstructor, node: yaml.MappingNode) -> bool:
    return ctor.construct_yaml_bool(node)  # type: ignore[no-untyped-call,no-any-return]


BaseConstructor.add_constructor("flow:bool", parse_bool)  # type: ignore


def parse_str(ctor: BaseConstructor, node: yaml.MappingNode) -> str:
    return str(ctor.construct_scalar(node))  # type: ignore[no-untyped-call]


BaseConstructor.add_constructor("flow:str", parse_str)  # type: ignore


def mark2pos(mark: yaml.Mark) -> Pos:
    return Pos(mark.line, mark.column, LocalPath(mark.name))


class SimpleCompound(Generic[_T, _Cont], abc.ABC):
    def __init__(self, factory: Type[Expr[_T]]) -> None:
        self._factory = factory

    @abc.abstractmethod
    def construct(self, ctor: BaseConstructor, node: yaml.Node) -> _Cont:
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


KeyT = Union[
    None,
    Type[Expr[Any]],
    SimpleCompound[Any, Any],
    Type[ast.Kind],
]
VarT = Union[
    None,
    Expr[Any],
    Mapping[str, Any],
    Sequence[Any],
    ast.Base,
    ast.Kind,
]

_AstType = TypeVar("_AstType", bound=ast.Base)
_CtorType = TypeVar("_CtorType", bound=BaseConstructor)


def parse_dict(
    ctor: _CtorType,
    node: yaml.MappingNode,
    keys: Mapping[str, KeyT],
    res_type: Type[_AstType],
    *,
    ret_name: Optional[str] = None,
    extra: Optional[Mapping[str, Union[str, LocalPath]]] = None,
    preprocess: Optional[
        Callable[[_CtorType, Dict[str, VarT]], Dict[str, VarT]]
    ] = None,
    find_res_type: Optional[
        Callable[[_CtorType, Type[_AstType], Dict[str, VarT]], Type[_AstType]]
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
            f"expected a mapping node, but found {node_id}",
            node.start_mark,
        )
    node_start = mark2pos(node.start_mark)
    node_end = mark2pos(node.end_mark)

    data = {}
    for k, v in node.value:
        key = ctor.construct_object(k)  # type: ignore[no-untyped-call]
        if key not in keys:
            raise ConstructorError(
                f"while constructing a {ret_name}",
                node.start_mark,
                f"unexpected key {key}",
                k.start_mark,
            )
        item_ctor: KeyT = keys[key]
        tmp: Any
        value: VarT
        if item_ctor is None:
            # Get constructor from tag
            value = ctor.construct_object(v)  # type: ignore[no-untyped-call]
        elif item_ctor is ast.Kind:
            tmp = str(ctor.construct_object(v))  # type: ignore[no-untyped-call]
            value = ast.Kind(tmp)
        elif isinstance(item_ctor, ast.Base):
            assert isinstance(
                v, ast.Base
            ), f"[{type(v)}] {v} should be ast.Base derived"
            value = v
        elif isinstance(item_ctor, SimpleCompound):
            value = item_ctor.construct(ctor, v)
        elif isinstance(item_ctor, type) and issubclass(item_ctor, Expr):
            tmp = str(ctor.construct_object(v))  # type: ignore[no-untyped-call]
            value = item_ctor(mark2pos(v.start_mark), mark2pos(v.end_mark), tmp)
        else:
            raise ConstructorError(
                f"while constructing a {ret_name}",
                node.start_mark,
                f"unexpected value tag {v.tag} for key {key}[{item_ctor}]",
                k.start_mark,
            )
        data[key] = value

    if preprocess is not None:
        data = preprocess(ctor, dict(data))
    if find_res_type is not None:
        res_type = find_res_type(ctor, res_type, dict(data))
        ret_name = res_type.__name__

    optional_fields: Dict[str, Any] = {}
    found_fields = extra.keys() | data.keys() | {"_start", "_end"}
    for f in dataclasses.fields(res_type):
        if f.name not in found_fields:
            key = f.name
            item_ctor = keys[key]
            if item_ctor is None:
                optional_fields[f.name] = None
            elif isinstance(item_ctor, SimpleCompound):
                optional_fields[f.name] = None
            elif isinstance(item_ctor, ast.Base):
                optional_fields[f.name] = None
            elif isinstance(item_ctor, type) and issubclass(item_ctor, Expr):
                if not item_ctor.allow_none:
                    raise ConstructorError(
                        f"while constructing a {ret_name}, "
                        f"missing mandatory key {f.name}",
                        node.start_mark,
                    )
                optional_fields[f.name] = item_ctor(node_start, node_end, None)
            else:
                raise ConstructorError(
                    f"while constructing a {ret_name}, "
                    f"unexpected {f.name} constructor type {item_ctor!r}",
                    node.start_mark,
                )
    return res_type(  # type: ignore[call-arg]
        _start=node_start,
        _end=node_end,
        **extra,
        **data,
        **optional_fields,
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


PROJECT = {
    "id": None,
}


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


def parse_project(
    workspace: LocalPath, *, filename: str = "project.yml"
) -> ast.Project:
    # Parse project config file
    ret: ast.Project
    config_file = workspace / filename
    try:
        with config_file.open() as f:
            loader = ProjectLoader(f)
            try:
                ret = loader.get_single_data()  # type: ignore[no-untyped-call]
                assert isinstance(ret, ast.Project)
                if not ret.id.isidentifier():
                    raise EvalError(
                        f"{ret.id!r} is not identifier", ret._start, ret._end
                    )
            finally:
                loader.dispose()  # type: ignore[no-untyped-call]
    except FileNotFoundError:
        ret = ast.Project(
            _start=Pos(0, 0, LocalPath("<default>")),
            _end=Pos(0, 0, LocalPath("<default>")),
            id=workspace.stem.replace("-", "_"),
        )
        if not ret.id.isidentifier():
            raise ValueError(
                f"{ret.id!r} is not identifier, "
                "please rename the project folder or "
                "specify id in project.yml"
            )
    return ret


# #### Flow parser ####


class FlowLoader(Reader, Scanner, Parser, Composer, BaseConstructor, BaseResolver):
    def __init__(self, stream: TextIO) -> None:
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseConstructor.__init__(self)
        BaseResolver.__init__(self)


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
            "build_args": SimpleSeq(StrExpr),
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
        {"matrix": None, "fail_fast": OptBoolExpr, "max_parallel": OptIntExpr},
        ast.Strategy,
    )


FlowLoader.add_path_resolver(  # type: ignore
    "flow:strategy", [(dict, "tasks"), (list, None), (dict, "strategy")]
)
FlowLoader.add_constructor("flow:strategy", parse_strategy)  # type: ignore


EXEC_UNIT = {
    "title": OptStrExpr,
    "name": OptStrExpr,
    "image": StrExpr,
    "preset": OptStrExpr,
    "entrypoint": OptStrExpr,
    "cmd": OptStrExpr,
    "bash": OptBashExpr,
    "python": OptPythonExpr,
    "workdir": OptRemotePathExpr,
    "env": SimpleMapping(StrExpr),
    "volumes": SimpleSeq(StrExpr),
    "tags": SimpleSeq(StrExpr),
    "life_span": OptLifeSpanExpr,
    "http_port": OptIntExpr,
    "http_auth": OptBoolExpr,
}


FlowLoader.add_path_resolver(  # type: ignore
    "flow:bool", [(dict, "jobs"), (dict, None), (dict, "multi")]
)


JOB = {
    "detach": OptBoolExpr,
    "browse": OptBoolExpr,
    "port_forward": SimpleSeq(PortPairExpr),
    "multi": None,
    **EXEC_UNIT,
}


def select_shells(ctor: BaseConstructor, dct: Dict[str, Any]) -> Dict[str, Any]:
    found = {k for k in dct if k in ("cmd", "bash", "python")}
    if len(found) > 1:
        raise ValueError(f"{','.join(found)} are mutually exclusive")

    bash = dct.pop("bash", None)
    if bash is not None:
        dct["cmd"] = bash

    python = dct.pop("python", None)
    if python is not None:
        dct["cmd"] = python

    return dct


def parse_job(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Job:
    return parse_dict(
        ctor, node, JOB, ast.Job, preprocess=select_shells  # type: ignore[arg-type]
    )


def parse_jobs(ctor: BaseConstructor, node: yaml.MappingNode) -> Dict[str, ast.Job]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_id(k)
        value = parse_job(ctor, v)
        ret[key] = value
    return ret


FlowLoader.add_path_resolver("flow:jobs", [(dict, "jobs")])  # type: ignore
FlowLoader.add_constructor("flow:jobs", parse_jobs)  # type: ignore


TASK = {
    "id": OptIdExpr,
    "needs": SimpleSeq(IdExpr),
    "strategy": None,
    **EXEC_UNIT,
}


def parse_task(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Task:
    return parse_dict(
        ctor, node, TASK, ast.Task, preprocess=select_shells  # type: ignore
    )


FlowLoader.add_path_resolver(  # type: ignore[no-untyped-call]
    "flow:task", [(dict, "tasks"), (list, None)]
)
FlowLoader.add_constructor("flow:task", parse_task)  # type: ignore


FlowLoader.add_path_resolver("flow:tasks", [(dict, "tasks")])  # type: ignore
FlowLoader.add_constructor("flow:tasks", FlowLoader.construct_sequence)  # type: ignore


def parse_flow_defaults(
    ctor: BaseConstructor, node: yaml.MappingNode
) -> ast.FlowDefaults:
    return parse_dict(
        ctor,
        node,
        {
            "tags": SimpleSeq(StrExpr),
            "env": SimpleMapping(StrExpr),
            "workdir": OptRemotePathExpr,
            "life_span": OptLifeSpanExpr,
            "preset": OptStrExpr,
        },
        ast.FlowDefaults,
    )


FlowLoader.add_path_resolver("flow:defaults", [(dict, "defaults")])  # type: ignore
FlowLoader.add_constructor("flow:defaults", parse_flow_defaults)  # type: ignore


FLOW = {
    "kind": ast.Kind,
    "id": None,
    "title": None,
    "images": None,
    "volumes": None,
    "defaults": None,
    "args": None,
    "jobs": None,
    "tasks": None,
}


FlowLoader.add_path_resolver("flow:str", [(dict, "title")])  # type: ignore
FlowLoader.add_path_resolver("flow:str", [(dict, "id")])  # type: ignore


FlowLoader.add_path_resolver(  # type: ignore
    "flow:str", [(dict, "args"), (dict, "default")]
)
FlowLoader.add_path_resolver(  # type: ignore
    "flow:str", [(dict, "args"), (dict, "descr")]
)


def parse_arg(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.Arg:
    return parse_dict(ctor, node, {"default": None, "descr": None}, ast.Arg)


def parse_args(ctor: BaseConstructor, node: yaml.MappingNode) -> Dict[str, ast.Arg]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_id(k)
        if isinstance(v, yaml.ScalarNode):
            default = ctor.construct_object(v)  # type: ignore[no-untyped-call]
            ret[key] = ast.Arg(
                _start=mark2pos(v.start_mark),
                _end=mark2pos(v.end_mark),
                default=str(default) if default is not None else None,
                descr=None,
            )
        else:
            arg = parse_arg(ctor, v)
            ret[key] = arg
    return ret


FlowLoader.add_path_resolver("flow:args", [(dict, "args")])  # type: ignore
FlowLoader.add_constructor("flow:args", parse_args)  # type: ignore


def select_kind(ctor: BaseConstructor, dct: Dict[str, Any]) -> Dict[str, Any]:
    if dct["kind"] == ast.Kind.LIVE:
        tasks = dct.pop("tasks", None)
        if tasks is not None:
            raise ValueError("flow of kind={dct['kind']} cannot have tasks")
        args = dct.pop("args", None)
        if args is not None:
            raise ValueError("flow of kind={dct['kind']} cannot have args")
    elif dct["kind"] == ast.Kind.BATCH:
        jobs = dct.pop("jobs", None)
        if jobs is not None:
            raise ValueError("flow of kind={dct['kind']} cannot have jobs")
        del dct["jobs"]
    else:
        raise ValueError(f"Unknown kind {dct['kind']} of the flow")
    return dct


def find_res_type(
    ctor: BaseConstructor, res_type: Type[ast.BaseFlow], arg: Dict[str, VarT]
) -> Type[ast.BaseFlow]:
    if arg["kind"] == ast.Kind.LIVE:
        return ast.LiveFlow
    elif arg["kind"] == ast.Kind.BATCH:
        return ast.BatchFlow
    else:
        raise ValueError(f"Unknown kind {arg['kind']} of the flow")


def parse_flow_main(ctor: BaseConstructor, node: yaml.MappingNode) -> ast.BaseFlow:
    ret = parse_dict(
        ctor,
        node,
        FLOW,
        ast.BaseFlow,
        find_res_type=find_res_type,
    )
    return ret


FlowLoader.add_path_resolver("flow:main", [])  # type: ignore
FlowLoader.add_constructor("flow:main", parse_flow_main)  # type: ignore


def parse_live(workspace: LocalPath, config_file: LocalPath) -> ast.LiveFlow:
    # Parse live flow config file
    with config_file.open() as f:
        loader = FlowLoader(f)
        try:
            ret = loader.get_single_data()  # type: ignore[no-untyped-call]
            assert isinstance(ret, ast.LiveFlow)
            assert ret.kind == ast.Kind.LIVE
            return ret
        finally:
            loader.dispose()  # type: ignore[no-untyped-call]


def parse_batch(workspace: LocalPath, config_file: LocalPath) -> ast.BatchFlow:
    # Parse pipeline flow config file
    with config_file.open() as f:
        loader = FlowLoader(f)
        try:
            ret = loader.get_single_data()  # type: ignore[no-untyped-call]
            assert isinstance(ret, ast.BatchFlow)
            assert ret.kind == ast.Kind.BATCH
            return ret
        finally:
            loader.dispose()  # type: ignore[no-untyped-call]


def find_workspace(path: Optional[Union[LocalPath, str]]) -> ConfigDir:
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


def find_live_config(workspace: ConfigDir) -> ConfigPath:
    # Find live config file, starting from path.
    # Return a project root folder and a path to config file.
    #
    # If path is a file -- it is used as is.
    # If path is a directory -- it is used as starting point, LocalPath.cwd() otherwise.
    # The lookup searches bottom-top from path dir up to the root folder,
    # looking for .neuro folder and ./neuro/live.yml
    # If the config file not found -- raise an exception.

    ret = workspace.config_dir / "live.yml"
    if not ret.exists():
        raise ValueError(f"{ret} does not exist")
    if not ret.is_file():
        raise ValueError(f"{ret} is not a file")
    return ConfigPath(workspace.workspace, ret)
