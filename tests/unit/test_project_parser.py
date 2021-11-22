import pathlib

from neuro_flow import ast
from neuro_flow.expr import (
    MappingItemsExpr,
    OptBashExpr,
    OptBoolExpr,
    OptIntExpr,
    OptLocalPathExpr,
    OptPythonExpr,
    OptRemotePathExpr,
    OptStrExpr,
    OptTimeDeltaExpr,
    RemotePathExpr,
    SequenceItemsExpr,
    SimpleIdExpr,
    SimpleOptStrExpr,
    StrExpr,
    URIExpr,
)
from neuro_flow.parser import parse_project_stream
from neuro_flow.tokenizer import Pos


def test_parse_full(assets: pathlib.Path) -> None:
    config_file = assets / "with_project_yaml" / "project.yml"
    with config_file.open() as stream:
        project = parse_project_stream(stream)
    assert project == ast.Project(
        Pos(0, 0, config_file),
        Pos(58, 0, config_file),
        id=SimpleIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "test_project",
        ),
        owner=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "test-owner",
        ),
        role=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "test-owner/roles/test-role",
        ),
        images={
            "image_a": ast.Image(
                Pos(5, 4, config_file),
                Pos(17, 0, config_file),
                ref=StrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "image:banana"
                ),
                context=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "dir"
                ),
                dockerfile=OptStrExpr(
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
                force_rebuild=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            )
        },
        volumes={
            "volume_a": ast.Volume(
                Pos(19, 4, config_file),
                Pos(23, 2, config_file),
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
                Pos(24, 4, config_file),
                Pos(26, 0, config_file),
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
        defaults=ast.BatchFlowDefaults(
            Pos(27, 2, config_file),
            Pos(42, 0, config_file),
            _specified_fields={
                "fail_fast",
                "tags",
                "cache",
                "env",
                "volumes",
                "life_span",
                "schedule_timeout",
                "workdir",
                "max_parallel",
                "preset",
            },
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
            cache=ast.Cache(
                Pos(40, 4, config_file),
                Pos(42, 0, config_file),
                strategy=ast.CacheStrategy.NONE,
                life_span=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "2h30m"
                ),
            ),
            fail_fast=OptBoolExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), False
            ),
            max_parallel=OptIntExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), 20),
        ),
        mixins={
            "basic": ast.ExecUnitMixin(
                Pos(44, 4, config_file),
                Pos(46, 2, config_file),
                _specified_fields={"image", "preset"},
                mixins=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=OptStrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "mixin-image",
                ),
                preset=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "mixin-preset"
                ),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
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
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
            "with_cmd": ast.ExecUnitMixin(
                Pos(47, 4, config_file),
                Pos(49, 2, config_file),
                _specified_fields={"image", "cmd"},
                mixins=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=OptStrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "mixin-image",
                ),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
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
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptStrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "command -o --option arg1 arg2",
                ),
            ),
            "with_bash": ast.ExecUnitMixin(
                Pos(50, 4, config_file),
                Pos(54, 2, config_file),
                _specified_fields={"image", "cmd"},
                mixins=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=OptStrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "mixin-image",
                ),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
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
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "command -o --option arg1 arg2\ncommand2 -o --option arg1 arg2\n",
                ),
            ),
            "with_python": ast.ExecUnitMixin(
                Pos(55, 4, config_file),
                Pos(58, 0, config_file),
                _specified_fields={"image", "cmd"},
                mixins=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=OptStrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "mixin-image",
                ),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                schedule_timeout=OptTimeDeltaExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
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
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptPythonExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    'print("hello neuro-flow")\n',
                ),
            ),
        },
    )
