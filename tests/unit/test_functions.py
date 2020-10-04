# test functions available in expressions

from typing import Mapping

from neuro_flow.expr import Pos, RootABC, StrExpr, TypeT
from neuro_flow.types import LocalPath


POS = Pos(0, 0, LocalPath(__file__))


class Root(RootABC):
    def __init__(self, mapping: Mapping[str, TypeT]) -> None:
        self._mapping = mapping

    def lookup(self, name: str) -> TypeT:
        return self._mapping[name]


async def test_len():
    expr = StrExpr(POS, POS, "${{ len('abc') }}")
    ret = await expr.eval(Root({}))
    assert ret == "3"


async def test_keys():
    expr = StrExpr(POS, POS, "${{ keys(dct) }}")
    ret = await expr.eval(Root({"dct": {"a": 1, "b": 2}}))
    assert ret == "['a', 'b']"


async def test_fmt():
    expr = StrExpr(POS, POS, "${{ fmt('{} {}', 1, 'a') }}")
    ret = await expr.eval(Root({}))
    assert ret == "1 a"


async def test_hash_files():
    expr = StrExpr(POS, POS, "${{ hash_files('Dockerfile', 'requirements/**.txt') }}")
    folder = LocalPath(__file__).parent / "hash_files"
    ret = await expr.eval(Root({"flow": {"workspace": folder}}))
    assert ret == "1 a"
