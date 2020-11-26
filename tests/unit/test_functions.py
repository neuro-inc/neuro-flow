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
    assert ret == "081fde04651e1184890a0470501bff3db8e0014260224e07acf5688e70e0edbe"


async def test_lower() -> None:
    expr = StrExpr(POS, POS, "${{ lower('aBcDeF') }}")
    ret = await expr.eval(Root({}))
    assert ret == "abcdef"


async def test_upper() -> None:
    expr = StrExpr(POS, POS, "${{ upper('aBcDeF') }}")
    ret = await expr.eval(Root({}))
    assert ret == "ABCDEF"


async def test_parse_volume_id() -> None:
    expr = StrExpr(POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').id }}")
    ret = await expr.eval(Root({}))
    assert ret == "ABCDEF"


async def test_parse_volume_remote() -> None:
    expr = StrExpr(
        POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').remote }}"
    )
    ret = await expr.eval(Root({}))
    assert ret == "ABCDEF"


async def test_parse_volume_mount() -> None:
    expr = StrExpr(
        POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').mount }}"
    )
    ret = await expr.eval(Root({}))
    assert ret == "ABCDEF"


async def test_parse_volume_read_only() -> None:
    expr = StrExpr(
        POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').read_only }}"
    )
    ret = await expr.eval(Root({}))
    assert ret == "ABCDEF"
