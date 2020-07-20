import pathlib

from neuro_flow import ast
from neuro_flow.expr import (
    IdExpr,
    OptBashExpr,
    OptBoolExpr,
    OptIdExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptLocalPathExpr,
    OptRemotePathExpr,
    OptStrExpr,
    RemotePathExpr,
    StrExpr,
    URIExpr,
)
from neuro_flow.parser import parse_pipeline


def test_parse_minimal(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "pipeline-minimal.yml"
    flow = parse_pipeline(workspace, config_file)
    assert flow == ast.PipelineFlow(
        (0, 0),
        (47, 0),
        id="pipeline-minimal",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title="Global title",
        images={
            "image_a": ast.Image(
                _start=(4, 4),
                _end=(11, 0),
                ref=StrExpr("image:banana"),
                context=OptLocalPathExpr("dir"),
                dockerfile=OptLocalPathExpr("dir/Dockerfile"),
                build_args=[StrExpr("--arg1"), StrExpr("val1"), StrExpr("--arg2=val2")],
            )
        },
        volumes={
            "volume_a": ast.Volume(
                _start=(13, 4),
                _end=(17, 2),
                remote=URIExpr("storage:dir"),
                mount=RemotePathExpr("/var/dir"),
                local=OptLocalPathExpr("dir"),
                read_only=OptBoolExpr("True"),
            ),
            "volume_b": ast.Volume(
                _start=(18, 4),
                _end=(20, 0),
                remote=URIExpr("storage:other"),
                mount=RemotePathExpr("/var/other"),
                local=OptLocalPathExpr(None),
                read_only=OptBoolExpr(None),
            ),
        },
        defaults=ast.FlowDefaults(
            _start=(21, 2),
            _end=(28, 0),
            tags=[StrExpr("tag-a"), StrExpr("tag-b")],
            env={"global_a": StrExpr("val-a"), "global_b": StrExpr("val-b")},
            workdir=OptRemotePathExpr("/global/dir"),
            life_span=OptLifeSpanExpr("1d4h"),
            preset=OptStrExpr("cpu-large"),
        ),
        batches=[
            ast.Batch(
                _start=(29, 4),
                _end=(47, 0),
                id=OptIdExpr("test_a"),
                title=OptStrExpr("Batch title"),
                needs=None,
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
                http_port=OptIntExpr("8080"),
                http_auth=OptBoolExpr("False"),
            )
        ],
    )


def test_parse_seq(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "pipeline-seq.yml"
    flow = parse_pipeline(workspace, config_file)
    assert flow == ast.PipelineFlow(
        (0, 0),
        (9, 0),
        id="pipeline-seq",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title=None,
        images=None,
        volumes=None,
        defaults=None,
        batches=[
            ast.Batch(
                _start=(2, 4),
                _end=(6, 2),
                id=OptIdExpr(None),
                title=OptStrExpr(None),
                needs=None,
                name=OptStrExpr(None),
                image=StrExpr("ubuntu"),
                preset=OptStrExpr("cpu-small"),
                entrypoint=OptStrExpr(None),
                cmd=OptBashExpr("echo abc"),
                workdir=OptRemotePathExpr(None),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(None),
                http_port=OptIntExpr(None),
                http_auth=OptBoolExpr(None),
            ),
            ast.Batch(
                _start=(6, 4),
                _end=(9, 0),
                id=OptIdExpr(None),
                title=OptStrExpr(None),
                needs=None,
                name=OptStrExpr(None),
                image=StrExpr("ubuntu"),
                preset=OptStrExpr("cpu-small"),
                entrypoint=OptStrExpr(None),
                cmd=OptBashExpr("echo def"),
                workdir=OptRemotePathExpr(None),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(None),
                http_port=OptIntExpr(None),
                http_auth=OptBoolExpr(None),
            ),
        ],
    )


def test_parse_needs(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "pipeline-needs.yml"
    flow = parse_pipeline(workspace, config_file)
    assert flow == ast.PipelineFlow(
        (0, 0),
        (11, 0),
        id="pipeline-needs",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title=None,
        images=None,
        volumes=None,
        defaults=None,
        batches=[
            ast.Batch(
                _start=(2, 4),
                _end=(7, 2),
                id=OptIdExpr("batch_a"),
                title=OptStrExpr(None),
                needs=None,
                name=OptStrExpr(None),
                image=StrExpr("ubuntu"),
                preset=OptStrExpr("cpu-small"),
                entrypoint=OptStrExpr(None),
                cmd=OptBashExpr("echo abc"),
                workdir=OptRemotePathExpr(None),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(None),
                http_port=OptIntExpr(None),
                http_auth=OptBoolExpr(None),
            ),
            ast.Batch(
                _start=(7, 4),
                _end=(11, 0),
                id=OptIdExpr(None),
                title=OptStrExpr(None),
                needs=[IdExpr("batch_a")],
                name=OptStrExpr(None),
                image=StrExpr("ubuntu"),
                preset=OptStrExpr("cpu-small"),
                entrypoint=OptStrExpr(None),
                cmd=OptBashExpr("echo def"),
                workdir=OptRemotePathExpr(None),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(None),
                http_port=OptIntExpr(None),
                http_auth=OptBoolExpr(None),
            ),
        ],
    )
