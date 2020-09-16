import pytest
from typing import Dict
from typing_extensions import Final

from neuro_flow.expr import PARSER, RootABC, TypeT
from neuro_flow.tokenizer import Pos, tokenize
from neuro_flow.types import LocalPath


FNAME = LocalPath("<test>")
START: Final = Pos(0, 0, FNAME)


class DictContext(RootABC):
    def lookup(self, name: str) -> TypeT:
        return self._dct[name]

    def __init__(self, dct: Dict[str, TypeT]) -> None:
        self._dct = dct


@pytest.mark.parametrize(  # type: ignore
    "expr,context,result",
    [
        ('"foo" == "foo"', {}, True),
        ('"foo" == "bar"', {}, False),
        ("4 < 5", {}, True),
        ("4 > 5", {}, False),
        ("(4 > 5) or ((4 <= 5))", {}, True),
        ("len(foo) <= 5", {"foo": [1, 2, 3]}, True),
        ("len(foo) >= 5", {"foo": [1, 2, 3]}, False),
        ("(2 == 3) or True", {}, True),
        ("'sdfdsf' == True", {}, False),
    ],
)
async def test_bool_evals(expr: str, context: Dict[str, TypeT], result: bool) -> None:
    parsed = PARSER.parse(list(tokenize("${{" + expr + "}}", START)))
    assert len(parsed) == 1
    assert result == await parsed[0].eval(DictContext(context))
