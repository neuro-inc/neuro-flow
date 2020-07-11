# YAML parser
#
# The parser converts YAML entities into ast data classes.
#
# Defaults are evaluated by the separate processing step.


import dataclasses
import datetime
import re
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, Optional, TextIO, Type, TypeVar, Union

import trafaret as t
import yaml
from yaml.constructor import ConstructorError, SafeConstructor
from yarl import URL

from . import ast
from .expr import (
    BoolExpr,
    OptBashExpr,
    OptBoolExpr,
    OptFloatExpr,
    OptIntExpr,
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
EXPR_RE = re.compile(r".*\$\{\{.+\}\}.*")
OptKey = partial(t.Key, optional=True)
Expr = t.WithRepr(t.String & t.Regexp(EXPR_RE), "<Expr>")
URI = t.WithRepr(Expr | (t.String & URL & str), "<URI>")


LocalPath = t.WithRepr(Expr | (t.String() & Path & str), "<LocalPath>")
RemotePath = t.WithRepr(Expr | (t.String() & PurePosixPath & str), "<RemotePath>")


def make_lifespan(match: "re.Match[str]") -> float:
    td = datetime.timedelta(
        days=int(match.group("d") or 0),
        hours=int(match.group("h") or 0),
        minutes=int(match.group("m") or 0),
        seconds=int(match.group("s") or 0),
    )
    return td.total_seconds()


RegexLifeSpan = (
    t.OnError(
        t.String
        & t.RegexpRaw(
            re.compile(r"^((?P<d>\d+)d)?((?P<h>\d+)h)?((?P<m>\d+)m)?((?P<s>\d+)s)?$")
        ),
        "value is not a lifespan, e.g. 1d2h3m4s",
    )
    & make_lifespan
)
LIFE_SPAN = t.WithRepr(Expr | t.Float & str | RegexLifeSpan & str, "<LifeSpan>")


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
            f"while constructing a {ret_name}",
            node.start_mark,
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
        if v.tag in (
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:float",
        ):
            value = str(ctor.construct_object(v))
        else:
            value = ctor.construct_scalar(v)
        data[key.replace("-", "_")] = keys[key](value)
    optional_fields = {}
    found_fields = extra.keys() | data.keys()
    for f in dataclasses.fields(res_type):
        if f.name not in found_fields:
            optional_fields[f.name] = keys[f.name.replace('_', '-')](None)
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


IMAGE = t.Dict(
    {
        t.Key("uri"): URI,
        OptKey("context"): LocalPath,
        OptKey("dockerfile"): LocalPath,
        OptKey("build-args"): t.List(t.String()),
    }
)


def parse_image(id: str, data: Dict[str, Any]) -> ast.Image:
    return ast.Image(
        id=id,
        uri=URIExpr(data["uri"]),
        context=OptLocalPathExpr(data.get("context")),
        dockerfile=OptLocalPathExpr(data.get("dockerfile")),
        build_args=[StrExpr(v) for v in data.get("build-args", [])],
    )


EXEC_UNIT = t.Dict(
    {
        OptKey("title"): t.String,
        OptKey("name"): t.String,
        t.Key("image"): t.String,
        OptKey("preset"): t.String,
        OptKey("entrypoint"): t.String,
        OptKey("cmd"): t.String,
        OptKey("bash"): t.String,
        OptKey("python"): t.String,
        OptKey("workdir"): RemotePath,
        t.Key("env", default=dict): t.Mapping(t.String, t.String),
        t.Key("volumes", default=list): t.List(t.String),
        t.Key("tags", default=list): t.List(t.String),
        OptKey("life-span"): Expr | LIFE_SPAN,
        OptKey("http-port"): Expr | t.Int & str,
        OptKey("http-auth"): Expr | t.Bool & str,
    }
)


def check_exec_unit(dct: Dict[str, Any]) -> Dict[str, Any]:
    found = sum(1 for k in dct if k in ("cmd", "bash", "python"))
    if found > 1:
        raise t.DataError
    return dct


def parse_exec_unit(id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    cmd_expr = OptStrExpr(data.get("cmd"))
    bash = data.get("bash")
    if bash is not None:
        cmd_expr = OptBashExpr(bash)
    python = data.get("python")
    if python is not None:
        cmd_expr = OptPythonExpr(python)
    return dict(
        id=id,
        title=OptStrExpr(data.get("title")),
        name=OptStrExpr(data.get("name")),
        image=StrExpr(data["image"]),
        preset=OptStrExpr(data.get("preset")),
        entrypoint=OptStrExpr(data.get("entrypoint")),
        cmd=cmd_expr,
        workdir=OptRemotePathExpr(data.get("workdir")),
        env={str(k): StrExpr(v) for k, v in data["env"].items()},
        volumes=[StrExpr(v) for v in data["volumes"]],
        tags={StrExpr(t) for t in data["tags"]},
        life_span=OptFloatExpr(data.get("life-span")),
        http_port=OptIntExpr(data.get("http-port")),
        http_auth=OptBoolExpr(data.get("http-auth")),
    )


JOB = t.WithRepr(
    t.OnError(
        EXEC_UNIT.merge(
            t.Dict(
                {
                    t.Key("detach", default=False): t.Bool & str,
                    t.Key("browse", default=False): t.Bool & str,
                }
            )
        )
        & check_exec_unit,
        "keys 'cmd', 'bash' and 'python' are mutually exclusive",
        code="mutually_exclusive_keys",
    ),
    "<JOB>",
)


def parse_job(id: str, data: Dict[str, Any]) -> ast.Job:
    return ast.Job(
        detach=BoolExpr(data["detach"]),
        browse=BoolExpr(data["browse"]),
        **parse_exec_unit(id, data),
    )


FLOW_DEFAULTS = t.Dict(
    {
        t.Key("tags", default=list): t.List(t.String),
        t.Key("env", default=dict): t.Mapping(t.String, t.String),
        OptKey("workdir"): RemotePath,
        OptKey("life-span"): LIFE_SPAN,
        OptKey("preset"): t.String,
    }
)


def parse_flow_defaults(data: Optional[Dict[str, Any]]) -> ast.FlowDefaults:
    if data is None:
        return ast.FlowDefaults(
            tags=set(),
            env={},
            workdir=OptRemotePathExpr(None),
            life_span=OptFloatExpr(None),
            preset=OptStrExpr(None),
        )
    return ast.FlowDefaults(
        tags={StrExpr(t) for t in data["tags"]},
        env={str(k): StrExpr(v) for k, v in data["env"].items()},
        workdir=OptRemotePathExpr(data.get("workdir")),
        life_span=OptFloatExpr(data.get("life-span")),
        preset=OptStrExpr(data.get("preset")),
    )


BASE_FLOW = t.Dict(
    {
        t.Key("kind"): t.String,
        OptKey("id"): t.String,
        OptKey("title"): t.String,
        t.Key("images", default=dict): t.Mapping(t.String, IMAGE),
        t.Key("volumes", default=dict): t.Mapping(t.String, t.Type(ast.Volume)),
        OptKey("defaults"): FLOW_DEFAULTS,
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
        images={
            str(id): parse_image(str(id), image) for id, image in data["images"].items()
        },
        volumes=data.get("volumes", {}),
        defaults=parse_flow_defaults(data.get("defaults")),
    )


INTERACTIVE_FLOW = BASE_FLOW.merge(t.Dict({t.Key("jobs"): t.Mapping(t.String, JOB)}))


def _parse_interactive(
    workspace: Path, default_id: str, data: Dict[str, Any]
) -> ast.InteractiveFlow:
    data = INTERACTIVE_FLOW(data)
    assert data["kind"] == ast.Kind.JOB.value
    jobs = {str(id): parse_job(str(id), job) for id, job in data["jobs"].items()}
    return ast.InteractiveFlow(
        jobs=jobs, **parse_base_flow(workspace, default_id, data)
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
