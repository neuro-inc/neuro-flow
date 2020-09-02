from neuro_flow import ast
from neuro_flow.expr import (
    OptBashExpr,
    OptBoolExpr,
    OptIntExpr,
    OptLifeSpanExpr,
    OptRemotePathExpr,
    OptStrExpr,
    SimpleOptBoolExpr,
    SimpleOptStrExpr,
    StrExpr,
)
from neuro_flow.parser import parse_action
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
