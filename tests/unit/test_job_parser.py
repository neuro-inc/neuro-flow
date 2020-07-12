import pathlib

from neuro_flow import ast
from neuro_flow.expr import (
    BoolExpr,
    OptBoolExpr,
    OptFloatExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptLocalPathExpr,
    OptRemotePathExpr,
    OptStrExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)
from neuro_flow.parser import parse_interactive


def test_parse_minimal(assets: pathlib.Path) -> None:
    flow = parse_interactive(assets, assets / "jobs-minimal.yml")
    assert flow == ast.InteractiveFlow(
        id="jobs-minimal",
        workspace=assets,
        kind=ast.Kind.JOB,
        title=OptStrExpr(None),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                id="test",
                name=OptStrExpr(None),
                image=StrExpr("ubuntu"),
                preset=OptStrExpr(None),
                entrypoint=OptStrExpr(None),
                cmd=OptStrExpr("echo abc"),
                workdir=OptRemotePathExpr(None),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(None),
                title=OptStrExpr(None),
                detach=OptBoolExpr(None),
                browse=OptBoolExpr(None),
                http_port=OptIntExpr(None),
                http_auth=OptBoolExpr(None),
            )
        },
    )


def test_parse_full(assets: pathlib.Path) -> None:
    flow = parse_interactive(assets, assets / "jobs-full.yml")
    assert flow == ast.InteractiveFlow(
        id="jobs-full",
        workspace=assets,
        kind=ast.Kind.JOB,
        title=OptStrExpr("Global title"),
        images={
            "image_a": ast.Image(
                id="image_a",
                uri=URIExpr("image:banana"),
                context=OptLocalPathExpr("dir/context"),
                dockerfile=OptLocalPathExpr("dir/Dockerfile"),
                build_args=[StrExpr("--arg1"), StrExpr("val1"), StrExpr("--arg2=val2")],
            )
        },
        volumes={
            "volume_a": ast.Volume(
                id="volume_a",
                uri=URIExpr("storage:dir"),
                mount=RemotePathExpr("/var/dir"),
                read_only=OptBoolExpr("True"),
                local=OptLocalPathExpr("dir"),
            ),
            "volume_b": ast.Volume(
                id="volume_b",
                uri=URIExpr("storage:other"),
                mount=RemotePathExpr("/var/other"),
                read_only=OptBoolExpr(None),
                local=OptLocalPathExpr(None),
            ),
        },
        defaults=ast.FlowDefaults(
            tags={StrExpr("tag-a"), StrExpr("tag-b")},
            env={"global_a": StrExpr("val-a"), "global_b": StrExpr("val-b")},
            workdir=OptRemotePathExpr("/global/dir"),
            life_span=OptLifeSpanExpr("1d4h"),
            preset=OptStrExpr("cpu-large"),
        ),
        jobs={
            "test-a": ast.Job(
                id="test-a",
                name=OptStrExpr("job-name"),
                image=StrExpr("${{ images.image_a.ref }}"),
                preset=OptStrExpr("cpu-small"),
                entrypoint=OptStrExpr("bash"),
                cmd=OptStrExpr("echo abc"),
                workdir=OptRemotePathExpr("/local/dir"),
                env={"local_a": StrExpr("val-1"), "local_b": StrExpr("val-2")},
                volumes=[
                    StrExpr("${{ volumes.volume_a.ref }}"),
                    StrExpr("storage:dir:/var/dir:ro"),
                ],
                tags={StrExpr("tag-2"), StrExpr("tag-1")},
                life_span=OptLifeSpanExpr("2h55m"),
                title=OptStrExpr("Job title"),
                detach=OptBoolExpr("True"),
                browse=OptBoolExpr("True"),
                http_port=OptIntExpr("8080"),
                http_auth=OptBoolExpr("False"),
            )
        },
    )
