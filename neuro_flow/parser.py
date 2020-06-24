from functools import partial
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Dict

import trafaret as t
import yaml
from yarl import URL

from . import ast


def _is_identifier(value: str) -> str:
    value.isidentifier()
    return value


def _beautify(filename: str) -> str:
    return filename.replace("_", " ").replace("-", " ").capitalize()


Id = t.WithRepr(
    t.OnError(
        t.String & str.isidentifier,
        "value is not an identifier",
        code="is_not_identifier",
    ),
    "<ID>",
)
OptKey = partial(t.Key, optional=True)
YarlURI = t.String() & URL
LocalPath = t.String() & Path
RemotePath = t.String() & PurePosixPath


VOLUME = t.Dict(
    {
        t.Key("id"): Id,
        t.Key("uri"): URL,
        t.Key("mount"): URL,
        t.Key("ro", default=False): t.Bool,
    }
)


IMAGE = t.Dict(
    {
        t.Key("id"): Id,
        t.Key("uri"): URL,
        t.Key("context"): LocalPath,
        t.Key("dockerfile"): LocalPath,
        t.Key("build-args"): t.Mapping(t.String(), t.String()),
    }
)


EXEC_UNIT = t.Dict(
    {
        OptKey("name"): t.String,
        t.Key("image"): t.String,
        OptKey("preset"): t.String,
        OptKey("http"): t.Dict(
            {t.Key("port"): t.Int, t.Key("require-auth", default=True): t.Bool}
        ),
        OptKey("entrypoint"): t.String,
        t.Key("cmd"): t.String,
        OptKey("workdir"): RemotePath,
        t.Key("env", default=dict): t.Mapping(t.String, t.String),
        t.Key("volumes", default=list): t.List(t.String),
        t.Key("tags", default=list): t.List(t.String),
        OptKey("life-span"): t.Int,
    }
)


def parse_exec_unit(data: Dict[str, Any]) -> Dict[str, Any]:
    return dict(
        name=data.get("name"),
        image=data["image"],
        preset=data.get("preset"),
        http=data.get("http"),
        entrypoint=data.get("entrypoint"),
        cmd=data["cmd"],
        workdir=data.get("workdir"),
        env=data["env"],
        volumes=data["volumes"],
        tags=frozenset(data["tags"]),
        life_span=data.get("life-span"),
    )


JOB = EXEC_UNIT.merge(
    t.Dict(
        {
            OptKey("title"): t.String,
            t.Key("detach", default=False): t.Bool,
            t.Key("browse", default=False): t.Bool,
        }
    )
)


def parse_job(id: str, data: Dict[str, Any]) -> ast.Job:
    return ast.Job(
        id=id,
        title=data.get("title") or id,
        detach=data["detach"],
        browse=data["browse"],
        **parse_exec_unit(data),
    )


BASE_FLOW = t.Dict(
    {
        t.Key("kind"): t.String,
        OptKey("title"): t.String,
        t.Key("images", default=list): t.List(IMAGE),
        t.Key("volumes", default=list): t.List(VOLUME),
        t.Key("tags", default=list): t.List(t.String),
        t.Key("env", default=dict): t.Mapping(t.String, t.String),
        OptKey("workdir"): RemotePath,
    }
)


def parse_base_flow(data: Dict[str, Any], path: Path) -> Dict[str, Any]:
    return dict(
        kind=ast.Kind(data["kind"]),
        title=data.get("title") or _beautify(path.stem),
        images=data["images"],
        volumes=data["volumes"],
        tags=frozenset(data["tags"]),
        env=MappingProxyType(data["env"]),
        workdir=data.get("workdir"),
    )


INTERACTIVE_FLOW = BASE_FLOW.merge(t.Dict({t.Key("jobs"): t.Mapping(t.String, JOB)}))


def parse_interactive(data: Dict[str, Any], path: Path) -> ast.InteractiveFlow:
    data = INTERACTIVE_FLOW(data)
    assert data["kind"] == ast.Kind.JOB.value
    jobs = {id: parse_job(id, job) for id, job in data["jobs"].items()}
    return ast.InteractiveFlow(jobs=jobs, **parse_base_flow(data, path))


def parse(path: Path) -> ast.BaseFlow:
    with path.open() as f:
        data = yaml.safe_load(f)
    kind = data.get("kind")
    if kind is None:
        raise RuntimeError("Missing field 'kind'")
    elif kind == ast.Kind.JOB.value:
        return parse_interactive(data, path)
    else:
        raise RuntimeError(
            f"Unknown 'kind': {kind}, supported values are 'job' and 'batch'"
        )
