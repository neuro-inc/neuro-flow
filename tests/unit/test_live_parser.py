import pathlib
import pytest
import yaml
from textwrap import dedent
from yaml.constructor import ConstructorError

from neuro_flow import ast
from neuro_flow.expr import (
    EvalError,
    MappingExpr,
    MappingItemsExpr,
    OptBashExpr,
    OptBoolExpr,
    OptIntExpr,
    OptLocalPathExpr,
    OptPythonExpr,
    OptRemotePathExpr,
    OptStrExpr,
    OptTimeDeltaExpr,
    PortPairExpr,
    RemotePathExpr,
    SequenceExpr,
    SequenceItemsExpr,
    SimpleOptBoolExpr,
    SimpleOptIdExpr,
    SimpleOptStrExpr,
    StrExpr,
    URIExpr,
    port_pair_item,
)
from neuro_flow.parser import parse_live, type2str
from neuro_flow.tokenizer import Pos


def test_parse_minimal(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-minimal.yml"
    flow = parse_live(workspace, config_file)
    assert flow == ast.LiveFlow(
        Pos(0, 0, config_file),
        Pos(5, 0, config_file),
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        kind=ast.FlowKind.LIVE,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                Pos(3, 4, config_file),
                Pos(5, 0, config_file),
                name=OptStrExpr(Pos(3, 4, config_file), Pos(5, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
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
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                detach=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                browse=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                port_forward=None,
                multi=SimpleOptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                params=None,
            )
        },
    )


def test_parse_params(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-params.yml"
    flow = parse_live(workspace, config_file)
    assert flow == ast.LiveFlow(
        Pos(0, 0, config_file),
        Pos(10, 0, config_file),
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        kind=ast.FlowKind.LIVE,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                Pos(3, 4, config_file),
                Pos(10, 0, config_file),
                name=OptStrExpr(Pos(3, 4, config_file), Pos(5, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "echo ${{ params.arg1 }} ${{ params.arg2 }}",
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                detach=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                browse=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                port_forward=None,
                multi=SimpleOptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                params={
                    "arg1": ast.Param(
                        _start=Pos(4, 12, config_file),
                        _end=Pos(4, 16, config_file),
                        default=SimpleOptStrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "val1"
                        ),
                        descr=SimpleOptStrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), None
                        ),
                    ),
                    "arg2": ast.Param(
                        _start=Pos(6, 8, config_file),
                        _end=Pos(8, 4, config_file),
                        default=SimpleOptStrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "val2"
                        ),
                        descr=SimpleOptStrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "Second arg"
                        ),
                    ),
                },
            )
        },
    )


def test_parse_full(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file)
    assert flow == ast.LiveFlow(
        Pos(0, 0, config_file),
        Pos(63, 0, config_file),
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        kind=ast.FlowKind.LIVE,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "Global title",
        ),
        images={
            "image_a": ast.Image(
                Pos(4, 4, config_file),
                Pos(16, 0, config_file),
                ref=StrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "image:banana"
                ),
                context=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir"
                ),
                dockerfile=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir/Dockerfile"
                ),
                build_args=SequenceItemsExpr(
                    [
                        StrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "--arg1"
                        ),
                        StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "val1"),
                        StrExpr(
                            Pos(0, 0, config_file),
                            Pos(0, 0, config_file),
                            "--arg2=val2",
                        ),
                    ]
                ),
                env=MappingItemsExpr(
                    {
                        "SECRET_ENV": StrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "secret:key"
                        ),
                    }
                ),
                volumes=SequenceItemsExpr(
                    [
                        OptStrExpr(
                            Pos(0, 0, config_file),
                            Pos(0, 0, config_file),
                            "secret:key:/var/secret/key.txt",
                        ),
                    ]
                ),
                build_preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "gpu-small"
                ),
            )
        },
        volumes={
            "volume_a": ast.Volume(
                Pos(18, 4, config_file),
                Pos(22, 2, config_file),
                remote=URIExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "storage:dir"
                ),
                mount=RemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "/var/dir"
                ),
                read_only=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                local=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir"
                ),
            ),
            "volume_b": ast.Volume(
                Pos(23, 4, config_file),
                Pos(25, 0, config_file),
                remote=URIExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "storage:other"
                ),
                mount=RemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "/var/other"
                ),
                read_only=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                local=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
        },
        defaults=ast.FlowDefaults(
            Pos(26, 2, config_file),
            Pos(36, 0, config_file),
            tags=SequenceItemsExpr(
                [
                    StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-a"),
                    StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-b"),
                ]
            ),
            env=MappingItemsExpr(
                {
                    "global_a": StrExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "val-a"
                    ),
                    "global_b": StrExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "val-b"
                    ),
                }
            ),
            volumes=SequenceItemsExpr(
                [
                    OptStrExpr(
                        Pos(0, 0, config_file),
                        Pos(0, 0, config_file),
                        "storage:common:/mnt/common:rw",
                    ),
                ]
            ),
            workdir=OptRemotePathExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "/global/dir"
            ),
            life_span=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "1d4h"
            ),
            preset=OptStrExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-large"
            ),
            schedule_timeout=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "24d23h22m21s"
            ),
        ),
        jobs={
            "test_a": ast.Job(
                Pos(38, 4, config_file),
                Pos(63, 0, config_file),
                name=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "job-name"
                ),
                image=StrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ images.image_a.ref }}",
                ),
                preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-micro"
                ),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "1d2h3m4s"
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
                env=MappingItemsExpr(
                    {
                        "local_a": StrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "val-1"
                        ),
                        "local_b": StrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "val-2"
                        ),
                    }
                ),
                volumes=SequenceItemsExpr(
                    [
                        OptStrExpr(
                            Pos(0, 0, config_file),
                            Pos(0, 0, config_file),
                            "${{ volumes.volume_a.ref }}",
                        ),
                        OptStrExpr(
                            Pos(0, 0, config_file),
                            Pos(0, 0, config_file),
                            "storage:dir:/var/dir:ro",
                        ),
                        OptStrExpr(
                            Pos(0, 0, config_file),
                            Pos(0, 0, config_file),
                            "",
                        ),
                        OptStrExpr(
                            Pos(0, 0, config_file),
                            Pos(0, 0, config_file),
                            None,
                        ),
                    ]
                ),
                tags=SequenceItemsExpr(
                    [
                        StrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-1"
                        ),
                        StrExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "tag-2"
                        ),
                    ]
                ),
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "2h55m"
                ),
                title=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "Job title"
                ),
                detach=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                browse=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), 8080
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), False
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                port_forward=SequenceItemsExpr(
                    [
                        PortPairExpr(
                            Pos(0, 0, config_file), Pos(0, 0, config_file), "2211:22"
                        )
                    ]
                ),
                multi=SimpleOptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                params=None,
            )
        },
    )


def test_parse_full_exprs(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full-exprs.yml"
    flow = parse_live(workspace, config_file)
    assert flow == ast.LiveFlow(
        Pos(0, 0, config_file),
        Pos(48, 0, config_file),
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        kind=ast.FlowKind.LIVE,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "Global title",
        ),
        images={
            "image_a": ast.Image(
                Pos(4, 4, config_file),
                Pos(11, 0, config_file),
                ref=StrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "image:banana"
                ),
                context=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir"
                ),
                dockerfile=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir/Dockerfile"
                ),
                build_args=SequenceExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ ['--arg1', 'val1', '--arg2=val2'] }}",
                    type2str,
                ),
                env=MappingExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ {'SECRET_ENV': 'secret:key' } }}",
                    type2str,
                ),
                volumes=SequenceExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ ['secret:key:/var/secret/key.txt'] }}",
                    type2str,
                ),
                build_preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "gpu-small"
                ),
            )
        },
        volumes={
            "volume_a": ast.Volume(
                Pos(13, 4, config_file),
                Pos(17, 2, config_file),
                remote=URIExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "storage:dir"
                ),
                mount=RemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "/var/dir"
                ),
                read_only=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                local=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir"
                ),
            ),
            "volume_b": ast.Volume(
                Pos(18, 4, config_file),
                Pos(20, 0, config_file),
                remote=URIExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "storage:other"
                ),
                mount=RemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "/var/other"
                ),
                read_only=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                local=OptLocalPathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
        },
        defaults=ast.FlowDefaults(
            Pos(21, 2, config_file),
            Pos(28, 0, config_file),
            tags=SequenceExpr(
                Pos(0, 0, config_file),
                Pos(0, 0, config_file),
                "${{ ['tag-a', 'tag-b'] }}",
                type2str,
            ),
            env=MappingExpr(
                Pos(0, 0, config_file),
                Pos(0, 0, config_file),
                "${{ {'global_a': 'val-a', 'global_b': 'val-b'} }}",
                type2str,
            ),
            volumes=SequenceExpr(
                Pos(0, 0, config_file),
                Pos(0, 0, config_file),
                "${{ ['storage:common:/mnt/common:rw'] }}",
                type2str,
            ),
            workdir=OptRemotePathExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "/global/dir"
            ),
            life_span=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "1d4h"
            ),
            preset=OptStrExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-large"
            ),
            schedule_timeout=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "24d23h22m21s"
            ),
        ),
        jobs={
            "test_a": ast.Job(
                Pos(30, 4, config_file),
                Pos(48, 0, config_file),
                name=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "job-name"
                ),
                image=StrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ images.image_a.ref }}",
                ),
                preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "cpu-micro"
                ),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "1d2h3m4s"
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
                env=MappingExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ {'local_a': 'val-1', 'local_b': 'val-2'} }}",
                    type2str,
                ),
                volumes=SequenceExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ [volumes.volume_a.ref, 'storage:dir:/var/dir:ro'] }}",
                    type2str,
                ),
                tags=SequenceExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ ['tag-1', 'tag-2'] }}",
                    type2str,
                ),
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "2h55m"
                ),
                title=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "Job title"
                ),
                detach=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                browse=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), 8080
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), False
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                port_forward=SequenceExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    '${{ ["2211:22"] }}',
                    port_pair_item,
                ),
                multi=SimpleOptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                params=None,
            )
        },
    )


def test_parse_bash(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-bash.yml"
    flow = parse_live(workspace, config_file)
    assert flow == ast.LiveFlow(
        Pos(0, 0, config_file),
        Pos(7, 0, config_file),
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        kind=ast.FlowKind.LIVE,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                Pos(3, 4, config_file),
                Pos(7, 0, config_file),
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "echo abc\necho def\n",
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                detach=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                browse=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                port_forward=None,
                multi=SimpleOptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                params=None,
            )
        },
    )


def test_parse_python(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-python.yml"
    flow = parse_live(workspace, config_file)
    assert flow == ast.LiveFlow(
        Pos(0, 0, config_file),
        Pos(7, 0, config_file),
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        kind=ast.FlowKind.LIVE,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                Pos(3, 4, config_file),
                Pos(7, 0, config_file),
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptPythonExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "import sys\nprint(sys.argv)\n",
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                detach=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                browse=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                port_forward=None,
                multi=SimpleOptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                params=None,
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
        f"""\
        invalid literal for int() with base 10: 'abc def'
          in "{config_file}", line 6, column 16"""
    )


def test_parse_multi(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-multi.yml"
    flow = parse_live(workspace, config_file)
    assert flow == ast.LiveFlow(
        Pos(0, 0, config_file),
        Pos(6, 0, config_file),
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        kind=ast.FlowKind.LIVE,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                Pos(3, 4, config_file),
                Pos(6, 0, config_file),
                name=OptStrExpr(Pos(3, 4, config_file), Pos(5, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
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
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                detach=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                browse=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                port_forward=None,
                multi=SimpleOptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), True
                ),
                params=None,
            )
        },
    )


def test_parse_explicit_flow_id(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-flow-id.yml"
    flow = parse_live(workspace, config_file)
    assert flow == ast.LiveFlow(
        Pos(0, 0, config_file),
        Pos(6, 0, config_file),
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "explicit_id",
        ),
        kind=ast.FlowKind.LIVE,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        images=None,
        volumes=None,
        defaults=None,
        jobs={
            "test": ast.Job(
                Pos(4, 4, config_file),
                Pos(6, 0, config_file),
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptStrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "echo abc",
                ),
                workdir=OptRemotePathExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                env=None,
                volumes=None,
                tags=None,
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                detach=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                browse=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                port_forward=None,
                multi=SimpleOptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                params=None,
            )
        },
    )


def test_live_job_extra_attrs(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-job-extra-attrs.yml"
    with pytest.raises(ConstructorError):
        parse_live(workspace, config_file)


def test_live_action_call_extra_attrs(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-action-call-extra-attrs.yml"
    with pytest.raises(ConstructorError):
        parse_live(workspace, config_file)
