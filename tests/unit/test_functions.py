# test functions available in expressions

from typing import Mapping

from neuro_flow.expr import RootABC, StrExpr, TypeT
from neuro_flow.tokenizer import Pos
from neuro_flow.types import LocalPath


POS = Pos(0, 0, LocalPath(__file__))


class Root(RootABC):
    def __init__(self, mapping: Mapping[str, TypeT]) -> None:
        self._mapping = mapping

    def lookup(self, name: str) -> TypeT:
        return self._mapping[name]


async def test_len() -> None:
    expr = StrExpr(POS, POS, "${{ len('abc') }}")
    ret = await expr.eval(Root({}))
    assert ret == "3"


async def test_keys() -> None:
    expr = StrExpr(POS, POS, "${{ keys(dct) }}")
    ret = await expr.eval(Root({"dct": {"a": 1, "b": 2}}))
    assert ret == "['a', 'b']"


async def test_fmt() -> None:
    expr = StrExpr(POS, POS, "${{ fmt('{} {}', 1, 'a') }}")
    ret = await expr.eval(Root({}))
    assert ret == "1 a"


async def test_hash_files() -> None:
    expr = StrExpr(POS, POS, "${{ hash_files('Dockerfile', 'requirements/*.txt') }}")
    folder = LocalPath(__file__).parent / "hash_files"
    ret = await expr.eval(Root({"flow": {"workspace": folder}}))
    assert ret == "8c310cbbd8acc18c57bc48bdc3da0efae33bb62ebaa87a58cf67a607dc9f35c4"
