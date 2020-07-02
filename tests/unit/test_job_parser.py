import pathlib

from neuro_flow import ast
from neuro_flow.expr import (
    BoolExpr,
    IntExpr,
    LocalPathExpr,
    OptFloatExpr,
    OptRemotePathExpr,
    OptStrExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)
from neuro_flow.parser import parse


def test_parse_minimal(assets: pathlib.Path) -> None:
    flow = parse(assets / "jobs-minimal.yml")
    assert flow == ast.InteractiveFlow(
        kind=ast.Kind.JOB,
        title=OptStrExpr(None),
        images={},
        volumes={},
        tags=set(),
        env={},
        workdir=OptRemotePathExpr(None),
        life_span=OptFloatExpr(None),
        jobs={
            "test": ast.Job(
                id="test",
                name=OptStrExpr(None),
                image=StrExpr("ubuntu"),
                preset=OptStrExpr(None),
                http=None,
                entrypoint=OptStrExpr(None),
                cmd=StrExpr("echo abc"),
                workdir=OptRemotePathExpr(None),
                env={},
                volumes=(),
                tags=set(),
                life_span=OptFloatExpr(None),
                title=OptStrExpr(None),
                detach=BoolExpr("False"),
                browse=BoolExpr("False"),
            )
        },
    )


def test_parse_full(assets: pathlib.Path) -> None:
    flow = parse(assets / "jobs-full.yml")
    assert flow == ast.InteractiveFlow(
        kind=ast.Kind.JOB,
        title=OptStrExpr("Global title"),
        images={
            "image_a": ast.Image(
                id="image_a",
                uri=URIExpr("image:banana"),
                context=LocalPathExpr("dir/context"),
                dockerfile=LocalPathExpr("dir/Dockerfile"),
                build_args={"arg1": StrExpr("val1"), "arg2": StrExpr("val2")},
            )
        },
        volumes={
            "volume_a": ast.Volume(
                id="volume_a",
                uri=URIExpr("storage:dir"),
                mount=RemotePathExpr("/var/dir"),
                ro=BoolExpr("True"),
            )
        },
        tags={StrExpr("tag-a"), StrExpr("tag-b")},
        env={"global_a": StrExpr("val-a"), "global_b": StrExpr("val-b")},
        workdir=OptRemotePathExpr("/global/dir"),
        life_span=OptFloatExpr("100800.0"),
        jobs={
            "test": ast.Job(
                id="test",
                name=OptStrExpr("job-name"),
                image=StrExpr("${{ images.image_a.ref }}"),
                preset=OptStrExpr("cpu-small"),
                http=ast.HTTPPort(
                    port=IntExpr("8080"), requires_auth=BoolExpr("False")
                ),
                entrypoint=OptStrExpr("bash"),
                cmd=StrExpr("echo abc"),
                workdir=OptRemotePathExpr("/local/dir"),
                env={"local_a": StrExpr("val-1"), "local_b": StrExpr("val-2")},
                volumes=(
                    StrExpr("${{ volumes.volume_a.ref }}"),
                    StrExpr("storage:dir:/var/dir:ro"),
                ),
                tags={StrExpr("tag-2"), StrExpr("tag-1")},
                life_span=OptFloatExpr("10500.0"),
                title=OptStrExpr("Job title"),
                detach=BoolExpr("True"),
                browse=BoolExpr("True"),
            )
        },
    )
