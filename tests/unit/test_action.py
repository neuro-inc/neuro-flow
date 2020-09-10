from unittest.mock import ANY

from neuro_flow import ast
from neuro_flow.expr import (
    OptBashExpr,
    OptBoolExpr,
    OptIdExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptRemotePathExpr,
    OptStrExpr,
    SimpleOptBoolExpr,
    SimpleOptIdExpr,
    SimpleOptStrExpr,
    StrExpr,
)
from neuro_flow.parser import parse_action, parse_live
from neuro_flow.tokenizer import Pos
from neuro_flow.types import LocalPath


def test_parse_live_action(assets: LocalPath) -> None:
    config_file = assets / "live-action.yml"
    action = parse_action(assets, config_file.name)
    assert action == ast.LiveAction(
        Pos(0, 0, config_file),
        Pos(16, 0, config_file),
        kind=ast.ActionKind.LIVE,
        name=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "Test live Action",
        ),
        author=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "Andrew Svetlov",
        ),
        descr=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "description of test action",
        ),
        inputs={
            "arg1": ast.Input(
                Pos(6, 4, config_file),
                Pos(7, 2, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "param 1"
                ),
                default=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
            "arg2": ast.Input(
                Pos(8, 4, config_file),
                Pos(10, 0, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "param 2"
                ),
                default=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "value 2"
                ),
            ),
        },
        outputs={
            "res": ast.Output(
                Pos(12, 4, config_file),
                Pos(13, 0, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "action result"
                ),
                value=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            )
        },
        job=ast.Job(
            Pos(14, 2, config_file),
            Pos(16, 0, config_file),
            name=OptStrExpr(Pos(3, 4, config_file), Pos(5, 0, config_file), None),
            image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
            preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            entrypoint=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            cmd=OptBashExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "echo abc"),
            workdir=OptRemotePathExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            env=None,
            volumes=None,
            tags=None,
            life_span=OptLifeSpanExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            detach=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            browse=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_port=OptIntExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_auth=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            port_forward=None,
            multi=SimpleOptBoolExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
        ),
    )


def test_parse_batch_action(assets: LocalPath) -> None:
    config_file = assets / "batch-action.yml"
    action = parse_action(assets, config_file.name)
    assert action == ast.BatchAction(
        Pos(0, 0, config_file),
        Pos(24, 0, config_file),
        kind=ast.ActionKind.BATCH,
        name=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "Test batch Action",
        ),
        author=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "Andrew Svetlov",
        ),
        descr=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "description of test action",
        ),
        inputs={
            "arg1": ast.Input(
                Pos(6, 4, config_file),
                Pos(7, 2, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "param 1"
                ),
                default=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
            "arg2": ast.Input(
                Pos(8, 4, config_file),
                Pos(10, 0, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "param 2"
                ),
                default=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "value 2"
                ),
            ),
        },
        outputs={
            "res1": ast.Output(
                Pos(ANY, ANY, config_file),
                Pos(ANY, ANY, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "action result 1"
                ),
                value=OptStrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ task_1.task1 }}",
                ),
            ),
            "res2": ast.Output(
                Pos(ANY, ANY, config_file),
                Pos(ANY, ANY, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "action result 2"
                ),
                value=OptStrExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ task_2.task2 }}",
                ),
            ),
        },
        tasks=[
            ast.Task(
                Pos(18, 2, config_file),
                Pos(21, 0, config_file),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "echo ::set-output name=task1::Task 1 ${{ inputs.arg1 }}",
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
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "task_1"),
                needs=None,
                strategy=None,
            ),
            ast.Task(
                Pos(21, 2, config_file),
                Pos(24, 0, config_file),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
                preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
                entrypoint=OptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                cmd=OptBashExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "echo ::set-output name=task2::Task 2 ${{ inputs.arg2 }}",
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
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "task_2"),
                needs=None,
                strategy=None,
            ),
        ],
    )


def test_parse_stateful_action(assets: LocalPath) -> None:
    config_file = assets / "stateful-action.yml"
    action = parse_action(assets, config_file.name)
    assert action == ast.StatefulAction(
        Pos(0, 0, config_file),
        Pos(24, 0, config_file),
        kind=ast.ActionKind.STATEFUL,
        name=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "Test stateful Action",
        ),
        author=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "Andrew Svetlov",
        ),
        descr=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            "description of test action",
        ),
        inputs={
            "arg1": ast.Input(
                Pos(6, 4, config_file),
                Pos(7, 2, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "param 1"
                ),
                default=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
            ),
            "arg2": ast.Input(
                Pos(8, 4, config_file),
                Pos(10, 0, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "param 2"
                ),
                default=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "value 2"
                ),
            ),
        },
        outputs={
            "res": ast.Output(
                Pos(12, 4, config_file),
                Pos(13, 0, config_file),
                descr=SimpleOptStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "action result"
                ),
                value=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            )
        },
        pre=ast.ExecUnit(
            Pos(14, 2, config_file),
            Pos(16, 0, config_file),
            title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
            preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            entrypoint=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            cmd=OptBashExpr(
                Pos(0, 0, config_file),
                Pos(0, 0, config_file),
                "echo ::set-state name=state1::State 1",
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
            http_port=OptIntExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_auth=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
        ),
        pre_if=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), True),
        main=ast.ExecUnit(
            Pos(18, 2, config_file),
            Pos(20, 0, config_file),
            title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
            preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            entrypoint=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            cmd=OptBashExpr(
                Pos(0, 0, config_file),
                Pos(0, 0, config_file),
                "echo ::set-state name=state2::State 2",
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
            http_port=OptIntExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_auth=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
        ),
        post=ast.ExecUnit(
            Pos(21, 2, config_file),
            Pos(23, 0, config_file),
            title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
            preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            entrypoint=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            cmd=OptBashExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "echo End"),
            workdir=OptRemotePathExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            env=None,
            volumes=None,
            tags=None,
            life_span=OptLifeSpanExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            http_port=OptIntExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_auth=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
        ),
        post_if=OptBoolExpr(
            Pos(0, 0, config_file), Pos(0, 0, config_file), "${{ True }}"
        ),
    )


def test_parse_live_call(assets: LocalPath) -> None:
    workspace = assets
    config_file = workspace / "live-action-call.yml"
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
            "test": ast.JobActionCall(
                Pos(3, 4, config_file),
                Pos(6, 0, config_file),
                action=StrExpr(
                    Pos(3, 4, config_file),
                    Pos(5, 0, config_file),
                    "workspace:live-action",
                ),
                args={
                    "arg1": StrExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "val 1"
                    )
                },
                # ## multi=SimpleOptBoolExpr(
                # ##     Pos(0, 0, config_file), Pos(0, 0, config_file), None
                # ## ),
            )
        },
    )
