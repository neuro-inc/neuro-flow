# test functions available in expressions
import sys
from neuromation.api import Client
from re_assert import Matches
from typing import AsyncIterator, Mapping

from neuro_flow.expr import RootABC, StrExpr, TypeT
from neuro_flow.tokenizer import Pos
from neuro_flow.types import LocalPath


if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


POS = Pos(0, 0, LocalPath(__file__))


class Root(RootABC):
    def __init__(self, mapping: Mapping[str, TypeT], client: Client) -> None:
        self._mapping = mapping
        self._client = client

    def lookup(self, name: str) -> TypeT:
        return self._mapping[name]

    @asynccontextmanager
    async def client(self) -> AsyncIterator[Client]:
        yield self._client


async def test_len(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ len('abc') }}")
    ret = await expr.eval(Root({}, client))
    assert ret == "3"


async def test_keys(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ keys(dct) }}")
    ret = await expr.eval(Root({"dct": {"a": 1, "b": 2}}, client))
    assert ret == "['a', 'b']"


async def test_fmt(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ fmt('{} {}', 1, 'a') }}")
    ret = await expr.eval(Root({}, client))
    assert ret == "1 a"


async def test_hash_files(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ hash_files('Dockerfile', 'requirements/*.txt') }}")
    folder = LocalPath(__file__).parent / "hash_files"
    ret = await expr.eval(Root({"flow": {"workspace": folder}}, client))
    assert ret == "081fde04651e1184890a0470501bff3db8e0014260224e07acf5688e70e0edbe"


async def test_lower(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ lower('aBcDeF') }}")
    ret = await expr.eval(Root({}, client))
    assert ret == "abcdef"


async def test_upper(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ upper('aBcDeF') }}")
    ret = await expr.eval(Root({}, client))
    assert ret == "ABCDEF"


async def test_parse_volume_id(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').id }}")
    ret = await expr.eval(Root({}, client))
    assert ret == "<volume>"


async def test_parse_volume_remote(client: Client) -> None:
    expr = StrExpr(
        POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').remote }}"
    )
    ret = await expr.eval(Root({}, client))
    assert Matches("storage:[^:]+/path/to") == ret


async def test_parse_volume_mount(client: Client) -> None:
    expr = StrExpr(
        POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').mount }}"
    )
    ret = await expr.eval(Root({}, client))
    assert ret == "/mnt/path"


async def test_parse_volume_read_only(client: Client) -> None:
    expr = StrExpr(
        POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').read_only }}"
    )
    ret = await expr.eval(Root({}, client))
    assert ret == "False"


async def test_parse_volume_local(client: Client) -> None:
    expr = StrExpr(
        POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').local }}"
    )
    ret = await expr.eval(Root({}, client))
    assert ret == "None"


async def test_parse_volume_local_full(client: Client) -> None:
    expr = StrExpr(
        POS, POS, "${{ parse_volume('storage:path/to:/mnt/path:rw').full_local_path }}"
    )
    ret = await expr.eval(Root({}, client))
    assert ret == "None"
