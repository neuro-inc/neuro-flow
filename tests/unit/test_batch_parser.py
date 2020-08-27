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
from neuro_flow.parser import parse_batch
from neuro_flow.tokenizer import Pos


def test_parse_minimal(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-minimal.yml"
    flow = parse_batch(workspace, config_file)
    assert flow == ast.BatchFlow(
        Pos(0, 0, config_file),
        Pos(47, 0, config_file),
        id="batch-minimal",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title="Global title",
        args=None,
        images={
            "image_a": ast.Image(
                _start=Pos(4, 4, config_file),
                _end=Pos(11, 0, config_file),
                ref=StrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "image:banana"
                ),
                context=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir"
                ),
                dockerfile=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir/Dockerfile"
                ),
                build_args=[
                    StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "--arg1"),
                    StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "val1"),
                    StrExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "--arg2=val2"
                    ),
                ],
            )
        },
        volumes={
            "volume_a": ast.Volume(
                _start=Pos(13, 4, config_file),
                _end=Pos(17, 2, config_file),
                remote=URIExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "storage:dir"
                ),
                mount=RemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "/var/dir"
                ),
                local=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir"
                ),
                read_only=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "True"
                ),
            ),
            "volume_b": ast.Volume(
                _start=Pos(18, 4, config_file),
                _end=Pos(20, 0, config_file),
                remote=URIExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "storage:other"
                ),
                mount=RemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "/var/other"
                ),
                local=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                read_only=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
        },
        defaults=ast.FlowDefaults(
            _start=Pos(21, 2, config_file),
            _end=Pos(28, 0, config_file),
            tags=[
                StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-a"),
                StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-b"),
            ],
            env={
                "global_a": StrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "val-a"
                ),
                "global_b": StrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "val-b"
                ),
            },
            workdir=OptRemotePathExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "/global/dir"
            ),
            life_span=OptLifeSpanExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "1d4h"
            ),
            preset=OptStrExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-large"
            ),
        ),
        tasks=[
            ast.Task(
                _start=Pos(29, 4, config_file),
                _end=Pos(47, 0, config_file),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "test_a"),
                title=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "Batch title"
                ),
                needs=None,
                name=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "job-name"
                ),
                image=StrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ images.image_a.ref }}",
                ),
                preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-small"
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "bash"
                ),
                cmd=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "echo abc"
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "/local/dir"
                ),
                env={
                    "local_a": StrExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "val-1"
                    ),
                    "local_b": StrExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "val-2"
                    ),
                },
                volumes=[
                    StrExpr(
                        Pos(0, 0, config_file),
                        Pos(0, 0, config_file),
                        "${{ volumes.volume_a.ref }}",
                    ),
                    StrExpr(
                        Pos(0, 0, config_file),
                        Pos(0, 0, config_file),
                        "storage:dir:/var/dir:ro",
                    ),
                ],
                tags=[
                    StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-1"),
                    StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-2"),
                ],
                life_span=OptLifeSpanExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "2h55m"
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "8080"
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "False"
                ),
                strategy=None,
            )
        ],
    )


def test_parse_seq(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-seq.yml"
    flow = parse_batch(workspace, config_file)
    assert flow == ast.BatchFlow(
        Pos(0, 0, config_file),
        Pos(9, 0, config_file),
        id="batch-seq",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title=None,
        args=None,
        images=None,
        volumes=None,
        defaults=None,
        tasks=[
            ast.Task(
                _start=Pos(2, 4, config_file),
                _end=Pos(6, 2, config_file),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                needs=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-small"
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "echo abc"
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                strategy=None,
            ),
            ast.Task(
                _start=Pos(6, 4, config_file),
                _end=Pos(9, 0, config_file),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                needs=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-small"
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "echo def"
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                strategy=None,
            ),
        ],
    )


def test_parse_needs(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-needs.yml"
    flow = parse_batch(workspace, config_file)
    assert flow == ast.BatchFlow(
        Pos(0, 0, config_file),
        Pos(11, 0, config_file),
        id="batch-needs",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title=None,
        args=None,
        images=None,
        volumes=None,
        defaults=None,
        tasks=[
            ast.Task(
                _start=Pos(2, 4, config_file),
                _end=Pos(7, 2, config_file),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "task_a"),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                needs=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-small"
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "echo abc"
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                strategy=None,
            ),
            ast.Task(
                _start=Pos(7, 4, config_file),
                _end=Pos(11, 0, config_file),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                needs=[
                    IdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "task_a")
                ],
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-small"
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "echo def"
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                strategy=None,
            ),
        ],
    )


def test_parse_matrix(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-matrix.yml"
    flow = parse_batch(workspace, config_file)
    assert flow == ast.BatchFlow(
        Pos(0, 0, config_file),
        Pos(15, 0, config_file),
        id="batch-matrix",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title=None,
        args=None,
        images=None,
        volumes=None,
        defaults=None,
        tasks=[
            ast.Task(
                _start=Pos(2, 4, config_file),
                _end=Pos(15, 0, config_file),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "echo abc"
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                needs=None,
                strategy=ast.Strategy(
                    _start=Pos(3, 6, config_file),
                    _end=Pos(13, 4, config_file),
                    matrix=ast.Matrix(
                        _start=Pos(4, 8, config_file),
                        _end=Pos(13, 4, config_file),
                        products={
                            "one": [
                                StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "o1"
                                ),
                                StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "o2"
                                ),
                            ],
                            "two": [
                                StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "t1"
                                ),
                                StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "t2"
                                ),
                            ],
                        },
                        exclude=[
                            {
                                "one": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "o1"
                                ),
                                "two": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "t2"
                                ),
                            }
                        ],
                        include=[
                            {
                                "one": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "o3"
                                ),
                                "two": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "t3"
                                ),
                                "extra": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "e3"
                                ),
                            }
                        ],
                    ),
                    fail_fast=OptBoolExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), None
                    ),
                    max_parallel=OptIntExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), None
                    ),
                ),
            )
        ],
    )


def test_parse_matrix_with_strategy(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-matrix-with-strategy.yml"
    flow = parse_batch(workspace, config_file)
    assert flow == ast.BatchFlow(
        Pos(0, 0, config_file),
        Pos(17, 0, config_file),
        id="batch-matrix-with-strategy",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title=None,
        args=None,
        images=None,
        volumes=None,
        defaults=None,
        tasks=[
            ast.Task(
                _start=Pos(2, 4, config_file),
                _end=Pos(17, 0, config_file),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "echo abc"
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                needs=None,
                strategy=ast.Strategy(
                    _start=Pos(3, 6, config_file),
                    _end=Pos(15, 4, config_file),
                    matrix=ast.Matrix(
                        _start=Pos(4, 8, config_file),
                        _end=Pos(13, 6, config_file),
                        products={
                            "one": [
                                StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "o1"
                                ),
                                StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "o2"
                                ),
                            ],
                            "two": [
                                StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "t1"
                                ),
                                StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "t2"
                                ),
                            ],
                        },
                        exclude=[
                            {
                                "one": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "o1"
                                ),
                                "two": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "t2"
                                ),
                            }
                        ],
                        include=[
                            {
                                "one": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "o3"
                                ),
                                "two": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "t3"
                                ),
                                "extra": StrExpr(
                                    Pos(0, 0, config_file), Pos(0, 0, config_file), "e3"
                                ),
                            }
                        ],
                    ),
                    fail_fast=OptBoolExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "True"
                    ),
                    max_parallel=OptIntExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "5"
                    ),
                ),
            )
        ],
    )


def test_parse_args(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-args.yml"
    flow = parse_batch(workspace, config_file)
    assert flow == ast.BatchFlow(
        Pos(0, 0, config_file),
        Pos(13, 0, config_file),
        id="batch-args",
        workspace=workspace,
        kind=ast.Kind.BATCH,
        title=None,
        args={
            "arg1": ast.Arg(
                _start=Pos(2, 8, config_file),
                _end=Pos(
                    2,
                    12,
                    config_file,
                ),
                default="val1",
                descr=None,
            ),
            "arg2": ast.Arg(
                _start=Pos(
                    4,
                    4,
                    config_file,
                ),
                _end=Pos(
                    6,
                    0,
                    config_file,
                ),
                default="val2",
                descr="descr2",
            ),
        },
        images=None,
        volumes=None,
        defaults=ast.FlowDefaults(
            _start=Pos(7, 2, config_file),
            _end=Pos(10, 0, config_file),
            tags=[
                StrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "${{ args.arg1 }}"
                ),
                StrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "${{ args.arg2 }}"
                ),
            ],
            env=None,
            workdir=OptRemotePathExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            life_span=OptLifeSpanExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
        ),
        tasks=[
            ast.Task(
                _start=Pos(
                    11,
                    4,
                    config_file,
                ),
                _end=Pos(
                    13,
                    0,
                    config_file,
                ),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "echo abc"
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptLifeSpanExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                needs=None,
                strategy=None,
            )
        ],
    )
