# YAML parser
#
# The parser converts YAML entities into ast data classes.
#
# Defaults are evaluated by the separate processing step.


import abc
import dataclasses
from functools import partial
from pathlib import Path
from typing import (
    AbstractSet,
    Any,
    Callable,
    Dict,
    Generic,
    Mapping,
    Optional,
    Sequence,
    TextIO,
    Type,
    TypeVar,
    Union,
)

import trafaret as t
import yaml
from yaml.composer import Composer
from yaml.constructor import ConstructorError, SafeConstructor
from yaml.parser import Parser
from yaml.reader import Reader
from yaml.resolver import Resolver
from yaml.scanner import Scanner

from . import ast
from .expr import (
    Expr,
    OptBashExpr,
    OptBoolExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptLocalPathExpr,
    OptPythonExpr,
    OptRemotePathExpr,
    OptStrExpr,
    Pos,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)
from .types import LocalPath


_T = TypeVar("_T")
_Cont = TypeVar("_Cont")


@dataclasses.dataclass
class ConfigPath:
    workspace: LocalPath
    config_file: LocalPath


class ConfigConstructor(SafeConstructor):
    def __init__(self, id: str, workspace: LocalPath) -> None:
        super().__init__()
        self._id = id
        self._workspace = workspace


class Loader(Reader, Scanner, Parser, Composer, ConfigConstructor, Resolver):
    def __init__(self, stream: TextIO, id: str, workspace: LocalPath) -> None:
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        ConfigConstructor.__init__(self, id, workspace)
        Resolver.__init__(self)


def _is_identifier(value: str) -> str:
    if not value.replace("-", "_").isidentifier():
        raise t.DataError
    return value


def mark2pos(mark: yaml.Mark) -> Pos:
    return (mark.line, mark.column)


Id = t.WithRepr(
    t.OnError(
        t.String & _is_identifier,
        "value is not an identifier",
        code="is_not_identifier",
    ),
    "<ID>",
)
OptKey = partial(t.Key, optional=True)


class SimpleCompound(Generic[_T, _Cont], abc.ABC):
    def __init__(self, factory: Callable[[str], _T]) -> None:
        self._factory = factory

    @abc.abstractmethod
    def construct(self, ctor: ConfigConstructor, node: yaml.Node) -> _Cont:
        pass


class SimpleSeq(SimpleCompound[_T, Sequence[_T]]):
    def construct(self, ctor: ConfigConstructor, node: yaml.Node) -> Sequence[_T]:
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
            val = ctor.construct_object(child)  # type: ignore[no-untyped-call]
            ret.append(self._factory(val))
        return ret


class SimpleSet(SimpleCompound[_T, AbstractSet[_T]]):
    def construct(self, ctor: ConfigConstructor, node: yaml.Node) -> AbstractSet[_T]:
        if not isinstance(node, yaml.SequenceNode):
            node_id = node.id  # type: ignore
            raise ConstructorError(
                None,
                None,
                f"expected a sequence node, but found {node_id}",
                node.start_mark,
            )
        ret = set()
        for child in node.value:
            val = ctor.construct_object(child)  # type: ignore[no-untyped-call]
            ret.add(self._factory(val))
        return ret


class SimpleMapping(SimpleCompound[_T, Mapping[str, _T]]):
    def construct(self, ctor: ConfigConstructor, node: yaml.Node) -> Mapping[str, _T]:
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
            key = ctor.construct_scalar(k)  # type: ignore[no-untyped-call]
            tmp = ctor.construct_scalar(v)  # type: ignore[no-untyped-call]
            value = self._factory(tmp)
            ret[key] = value
        return ret


ArgT = Union[
    None, Type[str], Type[Expr[Any]], SimpleCompound[Any, Any], Callable[..., ast.Base]
]
VarT = Union[
    str,
    Expr[Any],
    Mapping[str, Any],
    AbstractSet[Any],
    Sequence[Any],
    ast.Base,
    ast.Kind,
]

_AstType = TypeVar("_AstType", bound=ast.Base)


def parse_dict(
    ctor: ConfigConstructor,
    node: yaml.MappingNode,
    keys: Mapping[str, ArgT],
    res_type: Type[_AstType],
    *,
    ret_name: Optional[str] = None,
    extra: Optional[Mapping[str, Union[str, LocalPath]]] = None,
    preprocess: Optional[
        Callable[[ConfigConstructor, Dict[str, VarT]], Dict[str, VarT]]
    ] = None,
    find_res_type: Optional[
        Callable[[ConfigConstructor, Type[_AstType], Dict[str, VarT]], Type[_AstType]]
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
        item_ctor = keys[key]
        value: VarT
        if item_ctor is None:
            # Get constructor from tag
            value = ctor.construct_object(v)  # type: ignore[no-untyped-call]
        elif isinstance(item_ctor, ast.Base):
            assert isinstance(
                v, ast.Base
            ), f"[{type(v)}] {v} should be ast.Base derived"
            value = v
        elif isinstance(item_ctor, SimpleCompound):
            value = item_ctor.construct(ctor, v)
        elif v.tag in (
            "tag:yaml.org,2002:null",
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:float",
            "tag:yaml.org,2002:str",
        ):
            tmp = str(ctor.construct_object(v))  # type: ignore[no-untyped-call]
            value = item_ctor(tmp)
        else:
            raise ConstructorError(
                f"while constructing a {ret_name}",
                node.start_mark,
                f"unexpected value tag {v.tag}",
                k.start_mark,
            )
        data[key.replace("-", "_")] = value

    if preprocess is not None:
        data = preprocess(ctor, dict(data))
    if find_res_type is not None:
        res_type = find_res_type(ctor, res_type, dict(data))

    optional_fields: Dict[str, Any] = {}
    found_fields = extra.keys() | data.keys() | {"_start", "_end"}
    for f in dataclasses.fields(res_type):
        if f.name not in found_fields:
            key = f.name.replace("_", "-")
            item_ctor = keys[key]
            if item_ctor is None:
                optional_fields[f.name] = None
            elif isinstance(item_ctor, SimpleCompound):
                optional_fields[f.name] = None
            elif isinstance(item_ctor, ast.Base):
                optional_fields[f.name] = None
            else:
                optional_fields[f.name] = item_ctor(None)
    return res_type(  # type: ignore[call-arg]
        _start=mark2pos(node.start_mark),
        _end=mark2pos(node.end_mark),
        **extra,
        **data,
        **optional_fields,
    )


def parse_volume(
    ctor: ConfigConstructor, id: str, node: yaml.MappingNode
) -> ast.Volume:
    # uri -> URL
    # mount -> RemotePath
    # read-only -> bool [False]
    # local -> LocalPath [None]
    return parse_dict(
        ctor,
        node,
        {
            "uri": URIExpr,
            "mount": RemotePathExpr,
            "read-only": OptBoolExpr,
            "local": OptLocalPathExpr,
        },
        ast.Volume,
        extra={"id": id},
    )


def parse_volumes(
    ctor: ConfigConstructor, node: yaml.MappingNode
) -> Dict[str, ast.Volume]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_scalar(k)  # type: ignore[no-untyped-call]
        value = parse_volume(ctor, key, v)
        ret[key] = value
    return ret


Loader.add_path_resolver("flow:volumes", [(dict, "volumes")])  # type: ignore
Loader.add_constructor("flow:volumes", parse_volumes)  # type: ignore


def parse_image(ctor: ConfigConstructor, id: str, node: yaml.MappingNode) -> ast.Image:
    # uri -> URL
    # context -> LocalPath [None]
    # dockerfile -> LocalPath [None]
    # build-args -> List[str] [None]
    return parse_dict(
        ctor,
        node,
        {
            "uri": URIExpr,
            "context": OptLocalPathExpr,
            "dockerfile": OptLocalPathExpr,
            "build-args": SimpleSeq(StrExpr),
        },
        ast.Image,
        extra={"id": id},
    )


def parse_images(
    ctor: ConfigConstructor, node: yaml.MappingNode
) -> Dict[str, ast.Image]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_scalar(k)  # type: ignore[no-untyped-call]
        value = parse_image(ctor, key, v)
        ret[key] = value
    return ret


Loader.add_path_resolver("flow:images", [(dict, "images")])  # type: ignore
Loader.add_constructor("flow:images", parse_images)  # type: ignore


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
    "tags": SimpleSet(StrExpr),
    "life-span": OptLifeSpanExpr,
    "http-port": OptIntExpr,
    "http-auth": OptBoolExpr,
}

JOB = {"detach": OptBoolExpr, "browse": OptBoolExpr, **EXEC_UNIT}  # type: ignore


def preproc_job(ctor: ConfigConstructor, dct: Dict[str, Any]) -> Dict[str, Any]:
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


def parse_job(ctor: ConfigConstructor, id: str, node: yaml.MappingNode) -> ast.Job:
    return parse_dict(
        ctor, node, JOB, ast.Job, extra={"id": id}, preprocess=preproc_job
    )


def parse_jobs(ctor: ConfigConstructor, node: yaml.MappingNode) -> Dict[str, ast.Job]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_scalar(k)  # type: ignore[no-untyped-call]
        value = parse_job(ctor, key, v)
        ret[key] = value
    return ret


Loader.add_path_resolver("flow:jobs", [(dict, "jobs")])  # type: ignore
Loader.add_constructor("flow:jobs", parse_jobs)  # type: ignore


def parse_flow_defaults(
    ctor: ConfigConstructor, node: yaml.MappingNode
) -> ast.FlowDefaults:
    return parse_dict(
        ctor,
        node,
        {
            "tags": SimpleSet(StrExpr),
            "env": SimpleMapping(StrExpr),
            "workdir": OptRemotePathExpr,
            "life-span": OptLifeSpanExpr,
            "preset": OptStrExpr,
        },
        ast.FlowDefaults,
    )


Loader.add_path_resolver("flow:defaults", [(dict, "defaults")])  # type: ignore
Loader.add_constructor("flow:defaults", parse_flow_defaults)  # type: ignore


BASE_FLOW = {
    "kind": str,
    "id": str,
    "title": OptStrExpr,
    "images": None,
    "volumes": None,
    "defaults": None,
}


def preproc_flow(ctor: ConfigConstructor, arg: Dict[str, VarT]) -> Dict[str, VarT]:
    arg["kind"] = ast.Kind(arg["kind"])
    return arg


def find_res_type(
    ctor: ConfigConstructor, res_type: Type[ast.BaseFlow], arg: Dict[str, VarT]
) -> Type[ast.BaseFlow]:
    if arg["kind"] == ast.Kind.JOB:
        return ast.InteractiveFlow
    elif arg["kind"] == ast.Kind.JOB:
        return ast.BatchFlow
    else:
        raise ValueError(f"Unknown kind {arg['kind']} of the flow")


INTERACTIVE_FLOW = {"jobs": None, **BASE_FLOW}  # type: ignore[arg-type]


def parse_main(ctor: ConfigConstructor, node: yaml.MappingNode) -> ast.BaseFlow:
    return parse_dict(
        ctor,
        node,
        INTERACTIVE_FLOW,
        ast.BaseFlow,
        preprocess=preproc_flow,
        find_res_type=find_res_type,
        extra={"id": ctor._id, "workspace": ctor._workspace},
    )


Loader.add_path_resolver("flow:main", [])  # type: ignore
Loader.add_constructor("flow:main", parse_main)  # type: ignore


def parse_interactive(workspace: Path, config_file: Path) -> ast.InteractiveFlow:
    # Parse interactive flow config file
    with config_file.open() as f:
        loader = Loader(f, workspace.stem, workspace)
        try:
            ret = loader.get_single_data()  # type: ignore[no-untyped-call]
            assert isinstance(ret, ast.InteractiveFlow)
            assert ret.kind == ast.Kind.JOB
            return ret
        finally:
            loader.dispose()  # type: ignore[no-untyped-call]


def find_interactive_config(path: Optional[Union[Path, str]]) -> ConfigPath:
    # Find interactive config file, starting from path.
    # Return a project root folder and a path to config file.
    #
    # If path is a file -- it is used as is.
    # If path is a directory -- it is used as starting point, Path.cwd() otherwise.
    # The lookup searches bottom-top from path dir up to the root folder,
    # looking for .neuro folder and ./neuro/jobs.yml
    # If the config file not found -- raise an exception.

    if path is not None:
        if not isinstance(path, Path):
            path = Path(path)
        if not path.exists():
            raise ValueError(f"{path} does not exist")
        if not path.is_dir():
            raise ValueError(f"{path} should be a directory")
    else:
        path = Path.cwd()

    orig_path = path

    while True:
        if path == path.parent:
            raise ValueError(f".neuro folder was not found in lookup for {orig_path}")
        if (path / ".neuro").is_dir():
            break
        path = path.parent

    ret = path / ".neuro" / "jobs.yml"
    if not ret.exists():
        raise ValueError(f"{ret} does not exist")
    if not ret.is_file():
        raise ValueError(f"{ret} is not a file")
    return ConfigPath(path, ret)
