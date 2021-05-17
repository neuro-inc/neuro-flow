import pytest
from unittest.mock import ANY

from neuro_flow import ast
from neuro_flow.ast import BatchActionOutputs
from neuro_flow.expr import (
    EnableExpr,
    OptBashExpr,
    OptBoolExpr,
    OptIdExpr,
    OptIntExpr,
    OptRemotePathExpr,
    OptStrExpr,
    OptTimeDeltaExpr,
    SimpleOptBoolExpr,
    SimpleOptIdExpr,
    SimpleOptStrExpr,
    SimpleStrExpr,
    StrExpr,
)
from neuro_flow.parser import parse_action, parse_batch, parse_live
from neuro_flow.tokenizer import Pos
from neuro_flow.types import LocalPath


def test_parse_live_action(assets: LocalPath) -> None:
    config_file = assets / "live-action.yml"
    action = parse_action(config_file)
    assert action == ast.LiveAction(
        Pos(0, 0, config_file),
        Pos(13, 0, config_file),
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
        job=ast.Job(
            Pos(11, 2, config_file),
            Pos(13, 0, config_file),
            name=OptStrExpr(Pos(3, 4, config_file), Pos(5, 0, config_file), None),
            image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
            preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            schedule_timeout=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            entrypoint=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            cmd=OptBashExpr(
                Pos(0, 0, config_file),
                Pos(0, 0, config_file),
                "echo A ${{ inputs.arg1 }} B ${{ inputs.arg2 }} C",
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
            detach=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            browse=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_port=OptIntExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_auth=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            pass_config=OptBoolExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            port_forward=None,
            multi=SimpleOptBoolExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            params=None,
        ),
    )


def test_params_forbidden_in_live_action(assets: LocalPath) -> None:
    config_file = assets / "live-action-params.yml"
    with pytest.raises(
        ConnectionError,
        match=r"job.params is not supported inside "
        r"live action, use inputs instead.",
    ):
        parse_action(config_file)


def test_parse_batch_action(assets: LocalPath) -> None:
    config_file = assets / "batch-action.yml"
    action = parse_action(config_file)
    assert action == ast.BatchAction(
        Pos(0, 0, config_file),
        Pos(29, 0, config_file),
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
        outputs=BatchActionOutputs(
            Pos(ANY, ANY, config_file),
            Pos(ANY, ANY, config_file),
            values={
                "res1": ast.Output(
                    Pos(ANY, ANY, config_file),
                    Pos(ANY, ANY, config_file),
                    descr=SimpleOptStrExpr(
                        Pos(0, 0, config_file),
                        Pos(0, 0, config_file),
                        "action result 1",
                    ),
                    value=OptStrExpr(
                        Pos(0, 0, config_file),
                        Pos(0, 0, config_file),
                        "${{ needs.task_1.outputs.task1 }}",
                    ),
                ),
                "res2": ast.Output(
                    Pos(ANY, ANY, config_file),
                    Pos(ANY, ANY, config_file),
                    descr=SimpleOptStrExpr(
                        Pos(0, 0, config_file),
                        Pos(0, 0, config_file),
                        "action result 2",
                    ),
                    value=OptStrExpr(
                        Pos(0, 0, config_file),
                        Pos(0, 0, config_file),
                        "${{ needs.task_2.outputs.task2 }}",
                    ),
                ),
            },
        ),
        cache=ast.Cache(
            Pos(19, 2, config_file),
            Pos(21, 0, config_file),
            strategy=ast.CacheStrategy.INHERIT,
            life_span=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), "30m"
            ),
        ),
        tasks=[
            ast.Task(
                Pos(22, 2, config_file),
                Pos(26, 0, config_file),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
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
                    "echo ::set-output name=task1::Task 1 ${{ inputs.arg1 }}",
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
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "task_1"),
                needs={},
                strategy=None,
                cache=None,
                enable=EnableExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ success() }}",
                ),
            ),
            ast.Task(
                Pos(26, 2, config_file),
                Pos(29, 0, config_file),
                title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
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
                    "echo ::set-output name=task2::Task 2 ${{ inputs.arg2 }}",
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
                http_port=OptIntExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                http_auth=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                pass_config=OptBoolExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), None
                ),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "task_2"),
                needs=None,
                strategy=None,
                cache=None,
                enable=EnableExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ success() }}",
                ),
            ),
        ],
    )


def test_parse_stateful_action(assets: LocalPath) -> None:
    config_file = assets / "stateful_actions/parser-test.yml"
    action = parse_action(config_file)
    assert action == ast.StatefulAction(
        Pos(0, 0, config_file),
        Pos(19, 0, config_file),
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
        main=ast.ExecUnit(
            Pos(14, 2, config_file),
            Pos(16, 0, config_file),
            title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
            preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            schedule_timeout=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            entrypoint=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            cmd=OptBashExpr(
                Pos(0, 0, config_file),
                Pos(0, 0, config_file),
                "echo ::save-state name=state::State",
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
            http_port=OptIntExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_auth=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            pass_config=OptBoolExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
        ),
        post=ast.ExecUnit(
            Pos(17, 2, config_file),
            Pos(19, 0, config_file),
            title=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            name=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            image=StrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "ubuntu"),
            preset=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            schedule_timeout=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            entrypoint=OptStrExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            cmd=OptBashExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "echo End"),
            workdir=OptRemotePathExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            env=None,
            volumes=None,
            tags=None,
            life_span=OptTimeDeltaExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
            http_port=OptIntExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            http_auth=OptBoolExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), None),
            pass_config=OptBoolExpr(
                Pos(0, 0, config_file), Pos(0, 0, config_file), None
            ),
        ),
        post_if=EnableExpr(
            Pos(0, 0, config_file), Pos(0, 0, config_file), "${{ always() }}"
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
                action=SimpleStrExpr(
                    Pos(3, 4, config_file),
                    Pos(5, 0, config_file),
                    "workspace:live-action",
                ),
                args={
                    "arg1": StrExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "val 1"
                    )
                },
                params=None,
            )
        },
    )


def test_parse_batch_call(assets: LocalPath) -> None:
    workspace = assets
    config_file = workspace / "batch-action-call.yml"
    flow = parse_batch(workspace, config_file)
    assert flow == ast.BatchFlow(
        Pos(0, 0, config_file),
        Pos(6, 0, config_file),
        params=None,
        id=SimpleOptIdExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        kind=ast.FlowKind.BATCH,
        title=SimpleOptStrExpr(
            Pos(0, 0, config_file),
            Pos(0, 0, config_file),
            None,
        ),
        life_span=OptTimeDeltaExpr(
            Pos(0, 0, config_file), Pos(0, 0, config_file), None
        ),
        images=None,
        volumes=None,
        defaults=None,
        tasks=[
            ast.TaskActionCall(
                Pos(2, 2, config_file),
                Pos(6, 0, config_file),
                id=OptIdExpr(Pos(0, 0, config_file), Pos(0, 0, config_file), "test"),
                needs=None,
                strategy=None,
                cache=None,
                enable=EnableExpr(
                    Pos(0, 0, config_file),
                    Pos(0, 0, config_file),
                    "${{ success() }}",
                ),
                action=SimpleStrExpr(
                    Pos(0, 0, config_file), Pos(0, 0, config_file), "ws:batch-action"
                ),
                args={
                    "arg1": StrExpr(
                        Pos(0, 0, config_file), Pos(0, 0, config_file), "val 1"
                    )
                },
            )
        ],
    )
