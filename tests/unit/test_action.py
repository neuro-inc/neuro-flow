from neuro_flow import ast
from neuro_flow.parser import parse_action
from neuro_flow.types import LocalPath


def test_parse_live_action(assets: LocalPath) -> None:
    action = parse_action(assets, "live-action.yml")
    assert isinstance(action, ast.LiveAction)
