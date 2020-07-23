import pathlib
import pytest
import yaml
from textwrap import dedent

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
    PortPairExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
    EvalError,
)
from neuro_flow.parser import parse_live


def test_parse_minimal(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-minimal.yml"
    flow = parse_live(workspace, config_file, id=config_file.stem)
    assert flow == ast.LiveFlow(
        (0, 0),
        (5, 0),
        id="live-minimal",
        workspace=workspace,
        kind=ast.Kind.LIVE,
        title=None,
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                (3, 4),
                (5, 0),
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
                port_forward=None,
            )
        },
    )


def test_parse_full(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file, id=config_file.stem)
    assert flow == ast.LiveFlow(
        (0, 0),
        (51, 0),
        id="live-full",
        workspace=workspace,
        kind=ast.Kind.LIVE,
        title="Global title",
        images={
            "image_a": ast.Image(
                (4, 4),
                (11, 0),
                ref=StrExpr("image:banana"),
                context=OptLocalPathExpr("dir"),
                dockerfile=OptLocalPathExpr("dir/Dockerfile"),
                build_args=[StrExpr("--arg1"), StrExpr("val1"), StrExpr("--arg2=val2")],
            )
        },
        volumes={
            "volume_a": ast.Volume(
                (13, 4),
                (17, 2),
                remote=URIExpr("storage:dir"),
                mount=RemotePathExpr("/var/dir"),
                read_only=OptBoolExpr("True"),
                local=OptLocalPathExpr("dir"),
            ),
            "volume_b": ast.Volume(
                (18, 4),
                (20, 0),
                remote=URIExpr("storage:other"),
                mount=RemotePathExpr("/var/other"),
                read_only=OptBoolExpr(None),
                local=OptLocalPathExpr(None),
            ),
        },
        defaults=ast.FlowDefaults(
            (21, 2),
            (28, 0),
            tags=[StrExpr("tag-a"), StrExpr("tag-b")],
            env={"global_a": StrExpr("val-a"), "global_b": StrExpr("val-b")},
            workdir=OptRemotePathExpr("/global/dir"),
            life_span=OptLifeSpanExpr("1d4h"),
            preset=OptStrExpr("cpu-large"),
        ),
        jobs={
            "test_a": ast.Job(
                (30, 4),
                (51, 0),
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
                tags=[StrExpr("tag-1"), StrExpr("tag-2")],
                life_span=OptLifeSpanExpr("2h55m"),
                title=OptStrExpr("Job title"),
                detach=OptBoolExpr("True"),
                browse=OptBoolExpr("True"),
                http_port=OptIntExpr("8080"),
                http_auth=OptBoolExpr("False"),
                port_forward=[PortPairExpr("2211:22")],
            )
        },
    )


def test_parse_bash(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-bash.yml"
    flow = parse_live(workspace, config_file, id=config_file.stem)
    assert flow == ast.LiveFlow(
        (0, 0),
        (7, 0),
        id="live-bash",
        workspace=workspace,
        kind=ast.Kind.LIVE,
        title=None,
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                (3, 4),
                (7, 0),
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
                port_forward=None,
            )
        },
    )


def test_parse_python(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-python.yml"
    flow = parse_live(workspace, config_file, id=config_file.stem)
    assert flow == ast.LiveFlow(
        (0, 0),
        (7, 0),
        id="live-python",
        workspace=workspace,
        kind=ast.Kind.LIVE,
        title=None,
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                (3, 4),
                (7, 0),
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
                port_forward=None,
            )
        },
    )


def test_bad_job_name_not_identifier(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-bad-job-name.yml"
    with pytest.raises(yaml.MarkedYAMLError) as ctx:
        parse_live(workspace, config_file)
    assert ctx.value.problem == "bad-name-with-dash is not an identifier"
    assert str(ctx.value.problem_mark) == f'  in "{config_file}", line 3, column 3'


def test_bad_job_name_non_string(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-int-job-name.yml"
    with pytest.raises(yaml.MarkedYAMLError) as ctx:
        parse_live(workspace, config_file)
    assert ctx.value.problem == "expected a str, found <class 'int'>"
    assert str(ctx.value.problem_mark) == f'  in "{config_file}", line 3, column 3'


def test_bad_image_name(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-bad-image-name.yml"
    with pytest.raises(yaml.MarkedYAMLError) as ctx:
        parse_live(workspace, config_file)
    assert ctx.value.problem == "image-a is not an identifier"
    assert str(ctx.value.problem_mark) == f'  in "{config_file}", line 3, column 3'


def test_bad_volume_name(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-bad-volume-name.yml"
    with pytest.raises(yaml.MarkedYAMLError) as ctx:
        parse_live(workspace, config_file)
    assert ctx.value.problem == "volume-a is not an identifier"
    assert str(ctx.value.problem_mark) == f'  in "{config_file}", line 3, column 3'


def test_bad_expr_type_before_eval(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-bad-expr-type-before-eval.yml"
    with pytest.raises(EvalError) as ctx:
        parse_live(workspace, config_file)
    assert str(ctx.value) == dedent(
        """\
        'abc def' is not an int
          in line 6, column 16"""
    )
