import pathlib

from neuro_flow import ast
from neuro_flow.expr import (
    OptBashExpr,
    OptBoolExpr,
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
from neuro_flow.parser import parse_interactive


def test_parse_minimal(assets: pathlib.Path) -> None:
    workspace = assets / "jobs-minimal"
    config_file = workspace / ".neuro" / "jobs.yml"
    flow = parse_interactive(workspace, config_file)
    assert flow == ast.InteractiveFlow(
        (0, 0),
        (5, 0),
        id="jobs-minimal",
        workspace=workspace,
        kind=ast.Kind.JOB,
        title=OptStrExpr(None),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                (3, 4),
                (5, 0),
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
    workspace = assets / "jobs-full"
    config_file = workspace / ".neuro" / "jobs.yml"
    flow = parse_interactive(workspace, config_file)
    assert flow == ast.InteractiveFlow(
        (0, 0),
        (49, 0),
        id="jobs-full",
        workspace=workspace,
        kind=ast.Kind.JOB,
        title=OptStrExpr("Global title"),
        images={
            "image_a": ast.Image(
                (4, 4),
                (11, 0),
                id="image_a",
                uri=URIExpr("image:banana"),
                context=OptLocalPathExpr("dir/context"),
                dockerfile=OptLocalPathExpr("dir/Dockerfile"),
                build_args=[StrExpr("--arg1"), StrExpr("val1"), StrExpr("--arg2=val2")],
            )
        },
        volumes={
            "volume_a": ast.Volume(
                (13, 4),
                (17, 2),
                id="volume_a",
                uri=URIExpr("storage:dir"),
                mount=RemotePathExpr("/var/dir"),
                read_only=OptBoolExpr("True"),
                local=OptLocalPathExpr("dir"),
            ),
            "volume_b": ast.Volume(
                (18, 4),
                (20, 0),
                id="volume_b",
                uri=URIExpr("storage:other"),
                mount=RemotePathExpr("/var/other"),
                read_only=OptBoolExpr(None),
                local=OptLocalPathExpr(None),
            ),
        },
        defaults=ast.FlowDefaults(
            (21, 2),
            (28, 0),
            tags={StrExpr("tag-a"), StrExpr("tag-b")},
            env={"global_a": StrExpr("val-a"), "global_b": StrExpr("val-b")},
            workdir=OptRemotePathExpr("/global/dir"),
            life_span=OptLifeSpanExpr("1d4h"),
            preset=OptStrExpr("cpu-large"),
        ),
        jobs={
            "test-a": ast.Job(
                (30, 4),
                (49, 0),
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


def test_parse_bash(assets: pathlib.Path) -> None:
    workspace = assets / "jobs-bash"
    config_file = workspace / ".neuro" / "jobs.yml"
    flow = parse_interactive(workspace, config_file)
    assert flow == ast.InteractiveFlow(
        (0, 0),
        (7, 0),
        id="jobs-bash",
        workspace=workspace,
        kind=ast.Kind.JOB,
        title=OptStrExpr(None),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                (3, 4),
                (7, 0),
                id="test",
                name=OptStrExpr(None),
                image=StrExpr("ubuntu"),
                preset=OptStrExpr(None),
                entrypoint=OptStrExpr(None),
                cmd=OptBashExpr("echo abc\necho def\n"),
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


def test_parse_python(assets: pathlib.Path) -> None:
    workspace = assets / "jobs-python"
    config_file = workspace / ".neuro" / "jobs.yml"
    flow = parse_interactive(workspace, config_file)
    assert flow == ast.InteractiveFlow(
        (0, 0),
        (7, 0),
        id="jobs-python",
        workspace=workspace,
        kind=ast.Kind.JOB,
        title=OptStrExpr(None),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                (3, 4),
                (7, 0),
                id="test",
                name=OptStrExpr(None),
                image=StrExpr("ubuntu"),
                preset=OptStrExpr(None),
                entrypoint=OptStrExpr(None),
                cmd=OptPythonExpr("import sys\nprint(sys.argv)\n"),
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
