import pathlib
import pytest
from neuromation.api import JobStatus
from textwrap import dedent
from yarl import URL

from neuro_flow.context import (
    BatchActionContext,
    BatchContext,
    DepCtx,
    LiveContext,
    NotAvailable,
)
from neuro_flow.expr import EvalError
from neuro_flow.parser import parse_batch, parse_live
from neuro_flow.types import LocalPath, RemotePath


def test_inavailable_context_ctor() -> None:
    err = NotAvailable("job")
    assert err.args == ("The 'job' context is not available",)
    assert str(err) == "The 'job' context is not available"


async def test_ctx_flow(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-minimal.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    assert ctx.flow.flow_id == "live_minimal"
    assert ctx.flow.project_id == "unit"
    assert ctx.flow.workspace == workspace
    assert ctx.flow.title == "live_minimal"


async def test_env_defaults(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    assert ctx.env == {"global_a": "val-a", "global_b": "val-b"}


async def test_env_from_job(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    ctx = await ctx.with_meta("test_a")
    ctx2 = await ctx.with_job("test_a")
    assert ctx2.env == {
        "global_a": "val-a",
        "global_b": "val-b",
        "local_a": "val-1",
        "local_b": "val-2",
    }


async def test_volumes(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    assert ctx.volumes.keys() == {"volume_a", "volume_b"}

    assert ctx.volumes["volume_a"].id == "volume_a"
    assert ctx.volumes["volume_a"].remote == URL("storage:dir")
    assert ctx.volumes["volume_a"].mount == RemotePath("/var/dir")
    assert ctx.volumes["volume_a"].read_only
    assert ctx.volumes["volume_a"].local == LocalPath("dir")
    assert ctx.volumes["volume_a"].full_local_path == workspace / "dir"
    assert ctx.volumes["volume_a"].ref_ro == "storage:dir:/var/dir:ro"
    assert ctx.volumes["volume_a"].ref_rw == "storage:dir:/var/dir:rw"
    assert ctx.volumes["volume_a"].ref == "storage:dir:/var/dir:ro"

    assert ctx.volumes["volume_b"].id == "volume_b"
    assert ctx.volumes["volume_b"].remote == URL("storage:other")
    assert ctx.volumes["volume_b"].mount == RemotePath("/var/other")
    assert not ctx.volumes["volume_b"].read_only
    assert ctx.volumes["volume_b"].local is None
    assert ctx.volumes["volume_b"].full_local_path is None
    assert ctx.volumes["volume_b"].ref_ro == "storage:other:/var/other:ro"
    assert ctx.volumes["volume_b"].ref_rw == "storage:other:/var/other:rw"
    assert ctx.volumes["volume_b"].ref == "storage:other:/var/other:rw"


async def test_images(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    assert ctx.images.keys() == {"image_a"}

    assert ctx.images["image_a"].id == "image_a"
    assert ctx.images["image_a"].ref == "image:banana"
    assert ctx.images["image_a"].context == LocalPath("dir")
    assert ctx.images["image_a"].full_context_path == workspace / "dir"
    assert ctx.images["image_a"].dockerfile == LocalPath("dir/Dockerfile")
    assert ctx.images["image_a"].full_dockerfile_path == workspace / "dir/Dockerfile"
    assert ctx.images["image_a"].build_args == ["--arg1", "val1", "--arg2=val2"]


async def test_defaults(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    assert ctx.tags == {"tag-a", "tag-b", "project:unit", "flow:live-full"}
    assert ctx.defaults.workdir == RemotePath("/global/dir")
    assert ctx.defaults.life_span == 100800.0
    assert ctx.defaults.preset == "cpu-large"


async def test_job_root_ctx(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    with pytest.raises(NotAvailable):
        ctx.job


async def test_job(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-full.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    ctx = await ctx.with_meta("test_a")

    ctx2 = await ctx.with_job("test_a")
    assert ctx2.job.id == "test_a"
    assert ctx2.job.title == "Job title"
    assert ctx2.job.name == "job-name"
    assert ctx2.job.image == "image:banana"
    assert ctx2.job.preset == "cpu-small"
    assert ctx2.job.http_port == 8080
    assert not ctx2.job.http_auth
    assert ctx2.job.entrypoint == "bash"
    assert ctx2.job.cmd == "echo abc"
    assert ctx2.job.workdir == RemotePath("/local/dir")
    assert ctx2.job.volumes == ["storage:dir:/var/dir:ro", "storage:dir:/var/dir:ro"]
    assert ctx2.tags == {
        "tag-1",
        "tag-2",
        "tag-a",
        "tag-b",
        "project:unit",
        "flow:live-full",
        "job:test-a",
    }
    assert ctx2.job.life_span == 10500.0
    assert ctx2.job.port_forward == ["2211:22"]
    assert ctx2.job.detach
    assert ctx2.job.browse


async def test_bad_expr_type_after_eval(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-bad-expr-type-after-eval.yml"

    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    ctx = await ctx.with_meta("test")

    with pytest.raises(EvalError) as cm:
        await ctx.with_job("test")
    assert str(cm.value) == dedent(
        """\
        'abc def' is not an integer
          in line 5, column 19"""
    )


async def test_pipline_root_ctx(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-minimal.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)
    with pytest.raises(NotAvailable):
        ctx.task


async def test_pipeline_minimal_ctx(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-minimal.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    ctx2 = await ctx.with_task("test_a", needs={})
    assert ctx2.task.id == "test_a"
    assert ctx2.task.real_id == "test_a"
    assert ctx2.task.needs == set()
    assert ctx2.task.title == "Batch title"
    assert ctx2.task.name == "job-name"
    assert ctx2.task.image == "image:banana"
    assert ctx2.task.preset == "cpu-small"
    assert ctx2.task.http_port == 8080
    assert not ctx2.task.http_auth
    assert ctx2.task.entrypoint == "bash"
    assert ctx2.task.cmd == "echo abc"
    assert ctx2.task.workdir == RemotePath("/local/dir")
    assert ctx2.task.volumes == ["storage:dir:/var/dir:ro", "storage:dir:/var/dir:ro"]
    assert ctx2.tags == {
        "tag-1",
        "tag-2",
        "tag-a",
        "tag-b",
        "project:unit",
        "flow:batch-minimal",
    }
    assert ctx2.task.life_span == 10500.0

    assert ctx.graph == {"test_a": set()}
    assert ctx2.matrix == {}
    assert ctx2.strategy.max_parallel == 10
    assert not ctx2.strategy.fail_fast


async def test_pipeline_seq(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-seq.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    ctx2 = await ctx.with_task(
        "task-2", needs={"task-1": DepCtx(JobStatus.SUCCEEDED, {})}
    )
    assert ctx2.task.id is None
    assert ctx2.task.real_id == "task-2"
    assert ctx2.task.needs == {"task-1"}
    assert ctx2.task.title is None
    assert ctx2.task.name is None
    assert ctx2.task.image == "ubuntu"
    assert ctx2.task.preset == "cpu-small"
    assert ctx2.task.http_port is None
    assert not ctx2.task.http_auth
    assert ctx2.task.entrypoint is None
    assert ctx2.task.cmd == "bash -euo pipefail -c 'echo def'"
    assert ctx2.task.workdir is None
    assert ctx2.task.volumes == []
    assert ctx2.tags == {"project:unit", "flow:batch-seq", "task:task-2"}
    assert ctx2.task.life_span is None

    assert ctx.graph == {"task-2": {"task-1"}, "task-1": set()}
    assert ctx2.matrix == {}
    assert ctx2.strategy.max_parallel == 10
    assert not ctx2.strategy.fail_fast


async def test_pipeline_needs(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-needs.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(JobStatus.SUCCEEDED, {})}
    )
    assert ctx2.task.id is None
    assert ctx2.task.real_id == "task-2"
    assert ctx2.task.needs == {"task_a"}
    assert ctx2.task.title is None
    assert ctx2.task.name is None
    assert ctx2.task.image == "ubuntu"
    assert ctx2.task.preset == "cpu-small"
    assert ctx2.task.http_port is None
    assert not ctx2.task.http_auth
    assert ctx2.task.entrypoint is None
    assert ctx2.task.cmd == "bash -euo pipefail -c 'echo def'"
    assert ctx2.task.workdir is None
    assert ctx2.task.volumes == []
    assert ctx2.tags == {"project:unit", "flow:batch-needs", "task:task-2"}
    assert ctx2.task.life_span is None

    assert ctx.graph == {"task-2": {"task_a"}, "task_a": set()}
    assert ctx2.matrix == {}
    assert ctx2.strategy.max_parallel == 10
    assert not ctx2.strategy.fail_fast


async def test_pipeline_matrix(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-matrix.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    assert ctx.graph == {
        "task-1-e3-o3-t3": set(),
        "task-1-o1-t1": set(),
        "task-1-o2-t1": set(),
        "task-1-o2-t2": set(),
    }

    ctx2 = await ctx.with_task("task-1-o2-t2", needs={})
    assert ctx2.task.id is None
    assert ctx2.task.real_id == "task-1-o2-t2"
    assert ctx2.task.needs == set()
    assert ctx2.task.title is None
    assert ctx2.task.name is None
    assert ctx2.task.image == "ubuntu"
    assert ctx2.task.preset is None
    assert ctx2.task.http_port is None
    assert not ctx2.task.http_auth
    assert ctx2.task.entrypoint is None
    assert ctx2.task.cmd == "echo abc"
    assert ctx2.task.workdir is None
    assert ctx2.task.volumes == []
    assert ctx2.tags == {"project:unit", "flow:batch-matrix", "task:task-1-o2-t2"}
    assert ctx2.task.life_span is None

    assert ctx2.matrix == {"one": "o2", "two": "t2"}
    assert ctx2.strategy.max_parallel == 10
    assert not ctx2.strategy.fail_fast


async def test_pipeline_matrix_with_strategy(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-matrix-with-strategy.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    assert ctx.graph == {
        "task-1-e3-o3-t3": set(),
        "task-1-o1-t1": set(),
        "task-1-o2-t1": set(),
        "task-1-o2-t2": set(),
    }

    ctx2 = await ctx.with_task("task-1-e3-o3-t3", needs={})
    assert ctx2.task.id is None
    assert ctx2.task.real_id == "task-1-e3-o3-t3"
    assert ctx2.task.needs == set()
    assert ctx2.task.title is None
    assert ctx2.task.name is None
    assert ctx2.task.image == "ubuntu"
    assert ctx2.task.preset is None
    assert ctx2.task.http_port is None
    assert not ctx2.task.http_auth
    assert ctx2.task.entrypoint is None
    assert ctx2.task.cmd == "echo abc"
    assert ctx2.task.workdir is None
    assert ctx2.task.volumes == []
    assert ctx2.tags == {
        "project:unit",
        "flow:batch-matrix-with-strategy",
        "task:task-1-e3-o3-t3",
    }
    assert ctx2.task.life_span is None

    assert ctx2.matrix == {"extra": "e3", "one": "o3", "two": "t3"}
    assert ctx2.strategy.max_parallel == 5
    assert ctx2.strategy.fail_fast


async def test_pipeline_matrix_2(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-matrix-with-deps.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    assert ctx.graph == {
        "task-2-a-1": {"task_a"},
        "task-2-a-2": {"task_a"},
        "task-2-b-1": {"task_a"},
        "task-2-b-2": {"task_a"},
        "task-2-c-1": {"task_a"},
        "task-2-c-2": {"task_a"},
        "task_a": set(),
    }

    ctx2 = await ctx.with_task(
        "task-2-a-1", needs={"task_a": DepCtx(JobStatus.SUCCEEDED, {"name": "value"})}
    )
    assert ctx2.task.id is None
    assert ctx2.task.real_id == "task-2-a-1"
    assert ctx2.task.needs == {"task_a"}
    assert ctx2.task.title is None
    assert ctx2.task.name is None
    assert ctx2.task.image == "ubuntu"
    assert ctx2.task.preset == "cpu-small"
    assert ctx2.task.http_port is None
    assert not ctx2.task.http_auth
    assert ctx2.task.entrypoint is None
    assert ctx2.task.cmd == (
        """bash -euo pipefail -c \'echo "Task B a 1"\necho value\n\'"""
    )
    assert ctx2.task.workdir is None
    assert ctx2.task.volumes == []
    assert ctx2.tags == {
        "project:unit",
        "flow:batch-matrix-with-deps",
        "task:task-2-a-1",
    }
    assert ctx2.task.life_span is None

    assert ctx2.matrix == {"arg1": "a", "arg2": "1"}


async def test_pipeline_args(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-args.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    assert ctx.args == {"arg1": "val1", "arg2": "val2"}


async def test_batch_action_default(assets: pathlib.Path) -> None:
    workspace = assets
    ctx = await BatchActionContext.create("", "ws:batch-action.yml", workspace, set())
    assert ctx.outputs == {}
    assert ctx.state == {}
    with pytest.raises(NotAvailable):
        ctx.inputs


async def test_batch_action_with_inputs_unsupported(assets: pathlib.Path) -> None:
    workspace = assets
    ctx = await BatchActionContext.create("", "ws:batch-action.yml", workspace, set())

    with pytest.raises(ValueError, match=r"Unsupported input\(s\): other,unknown"):
        await ctx.with_inputs({"unknown": "value", "other": "val"})


async def test_batch_action_without_inputs_unsupported(assets: pathlib.Path) -> None:
    workspace = assets
    ctx = await BatchActionContext.create(
        "", "ws:batch-action-without-inputs", workspace, set()
    )

    with pytest.raises(ValueError, match=r"Unsupported input\(s\): unknown"):
        await ctx.with_inputs({"unknown": "value"})


async def test_batch_action_with_inputs_no_default(assets: pathlib.Path) -> None:
    workspace = assets
    ctx = await BatchActionContext.create("", "ws:batch-action.yml", workspace, set())

    with pytest.raises(ValueError, match=r"Required input\(s\): arg1"):
        await ctx.with_inputs({"arg2": "val2"})


async def test_batch_action_with_inputs_ok(assets: pathlib.Path) -> None:
    workspace = assets
    ctx = await BatchActionContext.create("", "ws:batch-action", workspace, set())

    ctx2 = await ctx.with_inputs({"arg1": "v1", "arg2": "v2"})
    assert ctx2.inputs == {"arg1": "v1", "arg2": "v2"}


async def test_batch_action_with_inputs_default_ok(assets: pathlib.Path) -> None:
    workspace = assets
    ctx = await BatchActionContext.create("", "ws:batch-action", workspace, set())

    ctx2 = await ctx.with_inputs({"arg1": "v1"})
    assert ctx2.inputs == {"arg1": "v1", "arg2": "value 2"}


async def test_job_with_live_action(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "live-action-call.yml"
    flow = parse_live(workspace, config_file)
    ctx = await LiveContext.create(flow, workspace, config_file)
    ctx = await ctx.with_meta("test")

    ctx2 = await ctx.with_job("test")
    assert ctx2.job.id == "test"
    assert ctx2.job.title == "live_action_call.test"
    assert ctx2.job.name is None
    assert ctx2.job.image == "ubuntu"
    assert ctx2.job.preset is None
    assert ctx2.job.http_port is None
    assert not ctx2.job.http_auth
    assert ctx2.job.entrypoint is None
    assert ctx2.job.cmd == "bash -euo pipefail -c 'echo A val 1 B value 2 C'"
    assert ctx2.job.workdir is None
    assert ctx2.job.volumes == []
    assert ctx2.tags == {
        "project:unit",
        "flow:live-action-call",
        "job:test",
    }
    assert ctx2.job.life_span is None
    assert ctx2.job.port_forward == []
    assert not ctx2.job.detach
    assert not ctx2.job.browse


async def test_pipeline_enable_default_no_needs(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-enable.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    ctx2 = await ctx.with_task("task_a", needs={})
    assert ctx2.task.enable


async def test_pipeline_enable_default_with_needs(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-needs.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    ctx2 = await ctx.with_task("task-2", needs={"task_a": DepCtx(JobStatus.FAILED, {})})
    assert not ctx2.task.enable

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(JobStatus.SUCCEEDED, {})}
    )
    assert ctx2.task.enable


async def test_pipeline_enable_success(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-enable.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    ctx2 = await ctx.with_task("task-2", needs={"task_a": DepCtx(JobStatus.FAILED, {})})
    assert not ctx2.task.enable

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(JobStatus.SUCCEEDED, {})}
    )
    assert ctx2.task.enable


async def test_pipeline_with_batch_action(assets: pathlib.Path) -> None:
    workspace = assets
    config_file = workspace / "batch-action-call.yml"
    flow = parse_batch(workspace, config_file)
    ctx = await BatchContext.create(flow, workspace, config_file)

    assert await ctx.is_action("test")
    ctx2 = await ctx.with_action("test", needs={})
    assert isinstance(ctx2, BatchActionContext)

    ctx3 = await ctx2.with_task("task_1", needs={})
    assert ctx3.task.id == "task_1"
    assert ctx3.task.real_id == "task_1"
    assert ctx3.task.needs == set()
    assert ctx3.task.title is None
    assert ctx3.task.name is None
    assert ctx3.task.image == "ubuntu"
    assert ctx3.task.preset is None
    assert ctx3.task.http_port is None
    assert not ctx3.task.http_auth
    assert ctx3.task.entrypoint is None
    assert (
        ctx3.task.cmd
        == "bash -euo pipefail -c 'echo ::set-output name=task1::Task 1 val 1'"
    )
    assert ctx3.task.workdir is None
    assert ctx3.task.volumes == []
    assert ctx3.tags == {"project:unit", "flow:batch-action-call", "task:test.task-1"}
    assert ctx3.task.life_span is None

    assert ctx3.graph == {"task_1": set(), "task_2": {"task_1"}}
    assert ctx3.matrix == {}
    assert ctx3.strategy.max_parallel == 10
    assert not ctx3.strategy.fail_fast
