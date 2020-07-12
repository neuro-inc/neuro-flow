# YAML parser
#
# The parser converts YAML entities into ast data classes.
#
# Defaults are evaluated by the separate processing step.


import abc
import dataclasses
import datetime
import re
from functools import partial
from pathlib import Path, PurePosixPath
from typing import (
    AbstractSet,
    Any,
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
from yaml.constructor import ConstructorError, SafeConstructor
from yarl import URL

from . import ast
from .expr import (
    BoolExpr,
    Expr,
    OptBashExpr,
    OptBoolExpr,
    OptFloatExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptLocalPathExpr,
    OptPythonExpr,
    OptRemotePathExpr,
    OptStrExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)
from .types import LocalPath as LocalPathT


_T = TypeVar("_T")
_Cont = TypeVar("_Cont")


@dataclasses.dataclass
class ConfigPath:
    workspace: LocalPathT
    config_file: LocalPathT


def _is_identifier(value: str) -> str:
    if not value.replace("-", "_").isidentifier():
        raise t.DataError
    return value


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
    @abc.abstractmethod
    def construct(self, ctor: SafeConstructor, node: yaml.SequenceNode) -> _Cont:
        pass


class SimpleSeq(SimpleCompound[_T, Sequence[_T]]):
    def __init__(self, item: Type[_T]) -> None:
        self._item = item

    def construct(self, ctor: SafeConstructor, node: yaml.SequenceNode) -> Sequence[_T]:
        if not isinstance(node, yaml.SequenceNode):
            raise ConstructorError(
                None,
                None,
                f"expected a sequence node, but found {node.id}",
                node.start_mark,
            )
        return [self._item(ctor.construct_object(child)) for child in node.value]


class SimpleSet(SimpleCompound[_T, AbstractSet[_T]]):
    def __init__(self, item: Type[_T]) -> None:
        self._item = item

    def construct(
        self, ctor: SafeConstructor, node: yaml.SequenceNode
    ) -> AbstractSet[_T]:
        if not isinstance(node, yaml.SequenceNode):
            raise ConstructorError(
                None,
                None,
                f"expected a sequence node, but found {node.id}",
                node.start_mark,
            )
        return {self._item(ctor.construct_object(child)) for child in node.value}


class SimpleMapping(SimpleCompound[_T, Mapping[str, _T]]):
    def __init__(self, item: Type[_T]) -> None:
        self._item = item

    def construct(
        self, ctor: SafeConstructor, node: yaml.SequenceNode
    ) -> AbstractSet[_T]:
        if not isinstance(node, yaml.MappingNode):
            raise ConstructorError(
                None,
                None,
                f"expected a mapping node, but found {node.id}",
                node.start_mark,
            )
        ret = {}
        for k, v in node.value:
            key = ctor.construct_scalar(k)
            value = self._item(ctor.construct_scalar(v))
            ret[key] = value
        return ret


def parse_dict(
    ctor: SafeConstructor,
    node: yaml.MappingNode,
    keys: Mapping[str, Union[Type[str], Type[Expr]]],
    extra: Mapping[str, Union[str]],
    res_type: Type[_T],
) -> _T:
    ret_name = res_type.__name__
    if not isinstance(node, yaml.MappingNode):
        raise ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node.id}",
            node.start_mark,
        )
    data = {}
    for k, v in node.value:
        key = ctor.construct_scalar(k)
        if key not in keys:
            raise ConstructorError(
                f"while constructing a {ret_name}",
                node.start_mark,
                f"unexpected key {key}",
                k.start_mark,
            )
        item_ctor = keys[key]
        if isinstance(item_ctor, SimpleCompound):
            value = item_ctor.construct(ctor, v)
        elif v.tag in (
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:float",
        ):
            value = item_ctor(str(ctor.construct_object(v)))
        else:
            value = item_ctor(ctor.construct_scalar(v))
        data[key.replace("-", "_")] = value
    optional_fields = {}
    found_fields = extra.keys() | data.keys()
    for f in dataclasses.fields(res_type):
        if f.name not in found_fields:
            key = f.name.replace("_", "-")
            item_ctor = keys[key]
            if isinstance(item_ctor, SimpleCompound):
                optional_fields[f.name] = None
            else:
                optional_fields[f.name] = item_ctor(None)
    return res_type(**extra, **data, **optional_fields)


def parse_volume(ctor: SafeConstructor, id: str, node: yaml.MappingNode) -> ast.Volume:
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
        {"id": id},
        ast.Volume,
    )


def parse_volumes(
    ctor: SafeConstructor, node: yaml.MappingNode
) -> Dict[str, ast.Volume]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_scalar(k)
        value = parse_volume(ctor, key, v)
        ret[key] = value
    return ret


yaml.SafeLoader.add_path_resolver("flow:volumes", [(dict, "volumes")])
yaml.SafeLoader.add_constructor("flow:volumes", parse_volumes)


def parse_image(ctor: SafeConstructor, id: str, node: yaml.MappingNode) -> ast.Image:
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
        {"id": id},
        ast.Image,
    )


def parse_images(
    ctor: SafeConstructor, node: yaml.MappingNode
) -> Dict[str, ast.Volume]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_scalar(k)
        value = parse_image(ctor, key, v)
        ret[key] = value
    return ret


yaml.SafeLoader.add_path_resolver("flow:images", [(dict, "images")])
yaml.SafeLoader.add_constructor("flow:images", parse_images)


def check_exec_unit(dct: Dict[str, Any]) -> Dict[str, Any]:
    found = sum(1 for k in dct if k in ("cmd", "bash", "python"))
    if found > 1:
        raise t.DataError
    return dct


EXEC_UNIT = {
    "title": OptStrExpr,
    "name": OptStrExpr,
    "image": StrExpr,
    "preset": OptStrExpr,
    "entrypoint": OptStrExpr,
    "cmd": OptStrExpr,
    "bash": OptStrExpr,
    "python": OptStrExpr,
    "workdir": OptRemotePathExpr,
    "env": SimpleMapping(StrExpr),
    "volumes": SimpleSeq(StrExpr),
    "tags": SimpleSet(StrExpr),
    "life-span": OptLifeSpanExpr,
    "http-port": OptIntExpr,
    "http-auth": OptBoolExpr,
}

JOB = {"detach": OptBoolExpr, "browse": OptBoolExpr, **EXEC_UNIT}


def parse_job(ctor: SafeConstructor, id: str, node: yaml.MappingNode) -> ast.Job:
    return parse_dict(ctor, node, JOB, {"id": id}, ast.Job)


def parse_jobs(ctor: SafeConstructor, node: yaml.MappingNode) -> Dict[str, ast.Volume]:
    ret = {}
    for k, v in node.value:
        key = ctor.construct_scalar(k)
        value = parse_job(ctor, key, v)
        ret[key] = value
    return ret


yaml.SafeLoader.add_path_resolver("flow:jobs", [(dict, "jobs")])
yaml.SafeLoader.add_constructor("flow:jobs", parse_jobs)


def parse_flow_defaults(
    ctor: SafeConstructor, node: yaml.MappingNode
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
        {},
        ast.FlowDefaults,
    )


yaml.SafeLoader.add_path_resolver("flow:defaults", [(dict, "defaults")])
yaml.SafeLoader.add_constructor("flow:defaults", parse_flow_defaults)

BASE_FLOW = t.Dict(
    {
        t.Key("kind"): t.String,
        OptKey("id"): t.String,
        OptKey("title"): t.String,
        OptKey("images"): t.Mapping(t.String, t.Type(ast.Image)),
        OptKey("volumes"): t.Mapping(t.String, t.Type(ast.Volume)),
        OptKey("defaults"): t.Type(ast.FlowDefaults),
    }
)


def parse_base_flow(
    workspace: Path, default_id: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    return dict(
        id=str(data.get("id", default_id)),
        workspace=workspace,
        kind=ast.Kind(data["kind"]),
        title=OptStrExpr(data.get("title")),
        images=data.get("images"),
        volumes=data.get("volumes"),
        defaults=data.get("defaults"),
    )


INTERACTIVE_FLOW = BASE_FLOW.merge(
    t.Dict({t.Key("jobs"): t.Mapping(t.String, t.Type(ast.Job))})
)


def _parse_interactive(
    workspace: Path, default_id: str, data: Dict[str, Any]
) -> ast.InteractiveFlow:
    data = INTERACTIVE_FLOW(data)
    assert data["kind"] == ast.Kind.JOB.value
    return ast.InteractiveFlow(
        jobs=data["jobs"], **parse_base_flow(workspace, default_id, data)
    )


def _calc_interactive_default_id(path: Path) -> str:
    if path.parts[-2:] == (".neuro", "jobs.yml"):
        default_id = path.parts[-3]
    else:
        default_id = path.stem
    return default_id


def parse_interactive(workspace: Path, config_file: Path) -> ast.InteractiveFlow:
    # Parse interactive flow config file
    with config_file.open() as f:
        data = yaml.load(f, yaml.SafeLoader)
        return _parse_interactive(
            workspace, _calc_interactive_default_id(config_file), data
        )


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
