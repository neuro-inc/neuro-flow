import pathlib

from apolo_flow import ast
from apolo_flow.expr import (
    ImageRefStrExpr,
    MappingItemsExpr,
    OptBashExpr,
    OptBoolExpr,
    OptImageRefStrExpr,
    OptIntExpr,
    OptLocalPathExpr,
    OptPythonExpr,
    OptRemotePathExpr,
    OptRestartPolicyExpr,
    OptStrExpr,
    OptTimeDeltaExpr,
    PlatformResourceURIExpr,
    RemotePathExpr,
    SequenceItemsExpr,
    SimpleIdExpr,
    SimpleOptStrExpr,
    StrExpr,
)
from apolo_flow.parser import parse_project_stream
from apolo_flow.tokenizer import Pos


def test_parse_full(assets: pathlib.Path) -> None:
    config_file = assets / "with_project_yaml" / "project.yml"
    with config_file.open() as stream:
        project = parse_project_stream(stream)
    assert project == ast.Project(
        Pos(0, 0, config_file),
        Pos(59, 0, config_file),
        id=SimpleIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "test_project",
        ),
        project_name=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "test-project-name",
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
                Pos(6, 4, config_file),
                Pos(18, 0, config_file),
                ref=ImageRefStrExpr(
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
                extra_kaniko_args=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            )
        },
        volumes={
            "volume_a": ast.Volume(
                Pos(20, 4, config_file),
                Pos(24, 2, config_file),
                remote=PlatformResourceURIExpr(
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
                Pos(25, 4, config_file),
                Pos(27, 0, config_file),
                remote=PlatformResourceURIExpr(
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
            Pos(28, 2, config_file),
            Pos(43, 0, config_file),
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
                Pos(41, 4, config_file),
                Pos(43, 0, config_file),
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
                Pos(45, 4, config_file),
                Pos(47, 2, config_file),
                _specified_fields={"image", "preset"},
                mixins=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=OptImageRefStrExpr(
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
                restart=OptRestartPolicyExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
            "with_cmd": ast.ExecUnitMixin(
                Pos(48, 4, config_file),
                Pos(50, 2, config_file),
                _specified_fields={"image", "cmd"},
                mixins=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=OptImageRefStrExpr(
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
                restart=OptRestartPolicyExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
            "with_bash": ast.ExecUnitMixin(
                Pos(51, 4, config_file),
                Pos(55, 2, config_file),
                _specified_fields={"image", "cmd"},
                mixins=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=OptImageRefStrExpr(
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
                restart=OptRestartPolicyExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
            "with_python": ast.ExecUnitMixin(
                Pos(56, 4, config_file),
                Pos(59, 0, config_file),
                _specified_fields={"image", "cmd"},
                mixins=None,
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=OptImageRefStrExpr(
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
                    'print("hello apolo-flow")\n',
                ),
                restart=OptRestartPolicyExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
        },
    )


def test_parse_minimal(assets: pathlib.Path) -> None:
    config_file = assets / "with_project_yaml" / "minimal_project.yaml"
    with config_file.open() as st:
        project = parse_project_stream(st)

    assert project == ast.Project(
        Pos(0, 0, config_file),
        Pos(1, 0, config_file),
        SimpleIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "myflow",
        ),
        project_name=SimpleOptStrExpr(
            Pos(0, 0, config_file), Pos(0, 0, config_file), pattern=None
        ),
        owner=SimpleOptStrExpr(
            Pos(0, 0, config_file), Pos(0, 0, config_file), pattern=None
        ),
        role=SimpleOptStrExpr(
            Pos(0, 0, config_file), Pos(0, 0, config_file), pattern=None
        ),
        images=None,
        volumes=None,
        defaults=None,
        mixins=None,
    )
