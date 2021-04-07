# test functions available in expressions
import pathlib
import pytest
import sys
from neuro_sdk import Client
from re_assert import Matches
from typing import AbstractSet, Any, AsyncIterator, Callable, Mapping

from neuro_flow.context import FlowCtx, LiveContext, TagsCtx
from neuro_flow.expr import EvalError, RootABC, StrExpr, TypeT
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


@pytest.mark.parametrize(
    "pattern,result",
    [
        ("'just string'", "just string"),
        ("True", "True"),
        ("222", "222"),
        ("22.22", "22.22"),
        ("[1, 2, 3]", "[1, 2, 3]"),
    ],
)
async def test_str(client: Client, pattern: str, result: str) -> None:
    expr = StrExpr(POS, POS, "${{ str(" + pattern + ") }}")
    ret = await expr.eval(Root({}, client))
    assert ret == result


async def test_replace(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ replace('22.22', '.', '_') }}")
    ret = await expr.eval(Root({}, client))
    assert ret == "22_22"


async def test_join(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ join('_', ['x', 'y', 'z']) }}")
    ret = await expr.eval(Root({}, client))
    assert ret == "x_y_z"


async def test_keys(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ keys(dct) }}")
    ret = await expr.eval(Root({"dct": {"a": 1, "b": 2}}, client))
    assert ret == "['a', 'b']"


async def test_values(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ values(dct) }}")
    ret = await expr.eval(Root({"dct": {"a": 1, "b": 2}}, client))
    assert ret == "[1, 2]"


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


LiveContextFactory = Callable[[Client, TagsCtx], LiveContext]


@pytest.fixture
async def live_context_factory(assets: pathlib.Path) -> LiveContextFactory:
    def _factory(client: Client, tags: TagsCtx = frozenset()) -> LiveContext:
        return LiveContext(
            _client=client,
            flow=FlowCtx(
                flow_id="live",
                project_id="test",
                workspace=assets,
                title="unit test flow",
            ),
            env={},
            images={},
            volumes={},
            tags=tags,
        )

    return _factory


async def test_inspect_job_bad_context(client: Client) -> None:
    expr = StrExpr(POS, POS, "${{ inspect_job(22) }}")
    with pytest.raises(
        EvalError, match=r"inspect_job\(\) is only available inside a job definition"
    ):
        await expr.eval(Root({}, client))


async def test_inspect_job_bad_first_arg(
    client: Client, live_context_factory: LiveContextFactory
) -> None:
    expr = StrExpr(POS, POS, "${{ inspect_job(22) }}")
    ctx = live_context_factory(client, set())
    with pytest.raises(
        EvalError, match=r"inspect_job\(\) job_name argument should be a str, got 22"
    ):
        await expr.eval(ctx)


async def test_inspect_job_bad_second_arg(
    client: Client, live_context_factory: LiveContextFactory
) -> None:
    expr = StrExpr(POS, POS, "${{ inspect_job('foo', 22) }}")
    ctx = live_context_factory(client, set())
    with pytest.raises(
        EvalError, match=r"inspect_job\(\) suffix argument should be a str, got 22"
    ):
        await expr.eval(ctx)


async def test_inspect_job_correct_set_of_tags(
    client: Client, live_context_factory: LiveContextFactory
) -> None:
    called = False

    async def fake_list(
        *args: Any, tags: AbstractSet[str], **kwargs: Any
    ) -> AsyncIterator[Any]:
        nonlocal called
        called = True
        assert tags == {"test_tag", "job:foo"}
        yield {"id": "test_id"}

    client.jobs.list = fake_list  # type: ignore

    expr = StrExpr(POS, POS, "${{ inspect_job('foo').id }}")

    ctx = live_context_factory(client, {"test_tag"})
    result = await expr.eval(ctx)
    assert result == "test_id"
    assert called


async def test_inspect_job_correct_set_of_tags_multi(
    client: Client, live_context_factory: LiveContextFactory
) -> None:
    called = False

    async def fake_list(
        *args: Any, tags: AbstractSet[str], **kwargs: Any
    ) -> AsyncIterator[Any]:
        nonlocal called
        called = True
        assert tags == {"test_tag", "job:foo", "multi:bar"}
        yield {"id": "test_id"}

    client.jobs.list = fake_list  # type: ignore

    expr = StrExpr(POS, POS, "${{ inspect_job('foo', 'bar').id }}")

    ctx = live_context_factory(client, {"test_tag"})
    result = await expr.eval(ctx)
    assert result == "test_id"
    assert called


async def test_inspect_job_no_jobs_errors(
    client: Client, live_context_factory: LiveContextFactory
) -> None:
    async def fake_list(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        # make it async iterator:
        for _ in range(0):
            yield None

    client.jobs.list = fake_list  # type: ignore

    expr = StrExpr(POS, POS, "${{ inspect_job('foo') }}")
    expr_with_suffix = StrExpr(POS, POS, "${{ inspect_job('foo', 'bar') }}")

    ctx = live_context_factory(client, set())
    with pytest.raises(
        EvalError, match=r"inspect_job\(\) did not found running job with name foo"
    ):
        await expr.eval(ctx)

    with pytest.raises(
        EvalError,
        match=r"inspect_job\(\) did not found running job with name foo"
        r" and suffix bar",
    ):
        await expr_with_suffix.eval(ctx)
