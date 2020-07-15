import pathlib

from neuro_flow.context import Context, NotAvailable
from neuro_flow.parser import parse_interactive


def test_inavailable_context_ctor() -> None:
    err = NotAvailable("job")
    assert err.args == ("Context job is not available",)
    assert str(err) == "Context job is not available"


async def test_ctx_flow(assets: pathlib.Path) -> None:
    workspace = assets / "jobs-minimal"
    config_file = workspace / ".neuro" / "jobs.yml"
    flow = parse_interactive(workspace, config_file)
    ctx = await Context.create(flow)
    assert ctx.flow.id == "jobs-minimal"
    assert ctx.flow.workspace == workspace
    assert ctx.flow.title == "jobs-minimal"


async def test_env_defaults(assets: pathlib.Path) -> None:
    workspace = assets / "jobs-full"
    config_file = workspace / ".neuro" / "jobs.yml"
    flow = parse_interactive(workspace, config_file)
    ctx = await Context.create(flow)
    assert ctx.env == {"global_a": "val-a", "global_b": "val-b"}


async def test_env_from_job(assets: pathlib.Path) -> None:
    workspace = assets / "jobs-full"
    config_file = workspace / ".neuro" / "jobs.yml"
    flow = parse_interactive(workspace, config_file)
    ctx = await Context.create(flow)
    ctx2 = await ctx.with_job("test_a")
    assert ctx2.env == {
        "global_a": "val-a",
        "global_b": "val-b",
        "local_a": "val-1",
        "local_b": "val-2",
    }
