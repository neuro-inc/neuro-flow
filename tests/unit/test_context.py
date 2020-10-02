import pathlib
import pytest
from textwrap import dedent
from yarl import URL

from neuro_flow import ast
from neuro_flow.config_loader import BatchLocalCL, ConfigLoader, LiveLocalCL
from neuro_flow.context import (
    BatchActionContext,
    BatchContext,
    CacheCtx,
    DepCtx,
    LiveContext,
    NotAvailable,
    StrategyCtx,
)
from neuro_flow.expr import EvalError
from neuro_flow.parser import ConfigDir
from neuro_flow.types import LocalPath, RemotePath, TaskStatus


def test_inavailable_context_ctor() -> None:
    err = NotAvailable("job")
    assert err.args == ("The 'job' context is not available",)
    assert str(err) == "The 'job' context is not available"


@pytest.fixture  # type: ignore
def live_config_loader(assets: pathlib.Path) -> ConfigLoader:
    config_dir = ConfigDir(
        workspace=assets,
        config_dir=assets,
    )
    return LiveLocalCL(config_dir)


@pytest.fixture  # type: ignore
def batch_config_loader(assets: pathlib.Path) -> ConfigLoader:
    config_dir = ConfigDir(
        workspace=assets,
        config_dir=assets,
    )
    return BatchLocalCL(config_dir)


async def test_ctx_flow(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-minimal")
    assert ctx.flow.flow_id == "live_minimal"
    assert ctx.flow.project_id == "unit"
    assert ctx.flow.workspace == live_config_loader.workspace
    assert ctx.flow.title == "live_minimal"


async def test_env_defaults(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-full")
    assert ctx.env == {"global_a": "val-a", "global_b": "val-b"}


async def test_env_from_job(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-full")
    ctx = await ctx.with_meta("test_a")
    ctx2 = await ctx.with_job("test_a")
    assert ctx2.env == {
        "global_a": "val-a",
        "global_b": "val-b",
        "local_a": "val-1",
        "local_b": "val-2",
    }


async def test_volumes(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-full")
    assert ctx.volumes.keys() == {"volume_a", "volume_b"}

    assert ctx.volumes["volume_a"].id == "volume_a"
    assert ctx.volumes["volume_a"].remote == URL("storage:dir")
    assert ctx.volumes["volume_a"].mount == RemotePath("/var/dir")
    assert ctx.volumes["volume_a"].read_only
    assert ctx.volumes["volume_a"].local == LocalPath("dir")
    assert (
        ctx.volumes["volume_a"].full_local_path == live_config_loader.workspace / "dir"
    )
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


async def test_images(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-full")
    assert ctx.images.keys() == {"image_a"}

    assert ctx.images["image_a"].id == "image_a"
    assert ctx.images["image_a"].ref == "image:banana"
    assert ctx.images["image_a"].context == LocalPath("dir")
    assert (
        ctx.images["image_a"].full_context_path == live_config_loader.workspace / "dir"
    )
    assert ctx.images["image_a"].dockerfile == LocalPath("dir/Dockerfile")
    assert (
        ctx.images["image_a"].full_dockerfile_path
        == live_config_loader.workspace / "dir/Dockerfile"
    )
    assert ctx.images["image_a"].build_args == ["--arg1", "val1", "--arg2=val2"]
    assert ctx.images["image_a"].env == {"SECRET_ENV": "secret:key"}
    assert ctx.images["image_a"].volumes == ["secret:key:/var/secret/key.txt"]


async def test_defaults(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-full")
    assert ctx.tags == {"tag-a", "tag-b", "project:unit", "flow:live-full"}
    assert ctx.defaults.workdir == RemotePath("/global/dir")
    assert ctx.defaults.life_span == 100800.0
    assert ctx.defaults.preset == "cpu-large"


async def test_job_root_ctx(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-full")
    with pytest.raises(NotAvailable):
        ctx.job


async def test_job(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-full")
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


async def test_bad_expr_type_after_eval(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-bad-expr-type-after-eval")
    ctx = await ctx.with_meta("test")

    with pytest.raises(EvalError) as cm:
        await ctx.with_job("test")
    assert str(cm.value) == dedent(
        """\
        'abc def' is not an integer
          in line 5, column 19"""
    )


async def test_pipline_root_ctx(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-minimal")
    with pytest.raises(NotAvailable):
        ctx.task


async def test_pipeline_minimal_ctx(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-minimal")

    ctx2 = await ctx.with_task("test_a", needs={})
    assert ctx2.task.id == "test_a"
    assert ctx2.task.full_id == ("test_a",)
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

    assert ctx.graph == {("test_a",): set()}
    assert ctx2.matrix == {}
    assert ctx2.strategy.max_parallel == 10
    assert ctx2.strategy.fail_fast


async def test_pipeline_seq(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-seq")

    ctx2 = await ctx.with_task(
        "task-2", needs={"task-1": DepCtx(TaskStatus.SUCCEEDED, {})}
    )
    assert ctx2.task.id is None
    assert ctx2.task.full_id == ("task-2",)
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

    assert ctx.graph == {("task-2",): {("task-1",)}, ("task-1",): set()}
    assert ctx2.matrix == {}
    assert ctx2.strategy.max_parallel == 10
    assert ctx2.strategy.fail_fast


async def test_pipeline_needs(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-needs")

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(TaskStatus.SUCCEEDED, {})}
    )
    assert ctx2.task.id is None
    assert ctx2.task.full_id == ("task-2",)
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

    assert ctx.graph == {("task-2",): {("task_a",)}, ("task_a",): set()}
    assert ctx2.matrix == {}
    assert ctx2.strategy.max_parallel == 10
    assert ctx2.strategy.fail_fast


async def test_pipeline_matrix(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-matrix")
    assert ctx.cache == CacheCtx(
        strategy=ast.CacheStrategy.DEFAULT,
        life_span=1209600,
    )

    assert ctx.graph == {
        ("task-1-e3-o3-t3",): set(),
        ("task-1-o1-t1",): set(),
        ("task-1-o2-t1",): set(),
        ("task-1-o2-t2",): set(),
    }

    ctx2 = await ctx.with_task("task-1-o2-t2", needs={})
    assert ctx2.task.id is None
    assert ctx2.task.full_id == ("task-1-o2-t2",)
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
    assert ctx2.strategy.fail_fast


async def test_pipeline_matrix_with_strategy(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-matrix-with-strategy")

    assert ctx.strategy.max_parallel == 15
    assert ctx.strategy.fail_fast
    assert ctx.cache == CacheCtx(
        strategy=ast.CacheStrategy.NONE,
        life_span=9000,
    )

    assert ctx.graph == {
        ("task-1-e3-o3-t3",): set(),
        ("task-1-o1-t1",): set(),
        ("task-1-o2-t1",): set(),
        ("task-1-o2-t2",): set(),
    }

    ctx2 = await ctx.with_task("task-1-e3-o3-t3", needs={})
    assert ctx2.task.id is None
    assert ctx2.task.full_id == ("task-1-e3-o3-t3",)
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
    assert not ctx2.strategy.fail_fast
    assert ctx2.cache == CacheCtx(
        strategy=ast.CacheStrategy.DEFAULT,
        life_span=5400,
    )


async def test_pipeline_matrix_2(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-matrix-with-deps")

    assert ctx.graph == {
        ("task-2-a-1",): {("task_a",)},
        ("task-2-a-2",): {("task_a",)},
        ("task-2-b-1",): {("task_a",)},
        ("task-2-b-2",): {("task_a",)},
        ("task-2-c-1",): {("task_a",)},
        ("task-2-c-2",): {("task_a",)},
        ("task_a",): set(),
    }

    assert ctx.cache == CacheCtx(
        strategy=ast.CacheStrategy.DEFAULT,
        life_span=1209600,
    )
    ctx2 = await ctx.with_task(
        "task-2-a-1", needs={"task_a": DepCtx(TaskStatus.SUCCEEDED, {"name": "value"})}
    )
    assert ctx2.task.id is None
    assert ctx2.task.full_id == ("task-2-a-1",)
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
    assert ctx2.cache == CacheCtx(
        strategy=ast.CacheStrategy.DEFAULT,
        life_span=1209600,
    )


async def test_pipeline_args(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-args")

    assert ctx.args == {"arg1": "val1", "arg2": "val2"}


async def test_batch_action_default(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchActionContext.create(
        (),
        "ws:batch-action.yml",
        batch_config_loader,
        set(),
        {"arg1": "val 1"},
        StrategyCtx(),
        CacheCtx(),
    )
    assert ctx.inputs == {"arg1": "val 1", "arg2": "value 2"}
    assert ctx.cache == CacheCtx(strategy=ast.CacheStrategy.NONE, life_span=1800)


async def test_batch_action_with_inputs_unsupported(
    batch_config_loader: ConfigLoader,
) -> None:
    with pytest.raises(ValueError, match=r"Unsupported input\(s\): other,unknown"):
        await BatchActionContext.create(
            (),
            "ws:batch-action.yml",
            batch_config_loader,
            set(),
            {"unknown": "value", "other": "val"},
            StrategyCtx(),
            CacheCtx(),
        )


async def test_batch_action_without_inputs_unsupported(
    batch_config_loader: ConfigLoader,
) -> None:
    with pytest.raises(ValueError, match=r"Unsupported input\(s\): unknown"):
        await BatchActionContext.create(
            (),
            "ws:batch-action-without-inputs",
            batch_config_loader,
            set(),
            {"unknown": "value"},
            StrategyCtx(),
            CacheCtx(),
        )


async def test_batch_action_with_inputs_no_default(
    batch_config_loader: ConfigLoader,
) -> None:
    with pytest.raises(ValueError, match=r"Required input\(s\): arg1"):
        await BatchActionContext.create(
            (),
            "ws:batch-action.yml",
            batch_config_loader,
            set(),
            {"arg2": "val2"},
            StrategyCtx(),
            CacheCtx(),
        )


async def test_batch_action_with_inputs_ok(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchActionContext.create(
        (),
        "ws:batch-action",
        batch_config_loader,
        set(),
        {"arg1": "v1", "arg2": "v2"},
        StrategyCtx(),
        CacheCtx(),
    )

    assert ctx.inputs == {"arg1": "v1", "arg2": "v2"}


async def test_batch_action_with_inputs_default_ok(
    batch_config_loader: ConfigLoader,
) -> None:
    ctx = await BatchActionContext.create(
        (),
        "ws:batch-action",
        batch_config_loader,
        set(),
        {"arg1": "v1"},
        StrategyCtx(),
        CacheCtx(),
    )

    assert ctx.inputs == {"arg1": "v1", "arg2": "value 2"}


async def test_job_with_live_action(live_config_loader: ConfigLoader) -> None:
    ctx = await LiveContext.create(live_config_loader, "live-action-call")
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


async def test_pipeline_enable_default_no_needs(
    batch_config_loader: ConfigLoader,
) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-enable")

    ctx2 = await ctx.with_task("task_a", needs={})
    assert ctx2.task.enable


async def test_pipeline_enable_default_with_needs(
    batch_config_loader: ConfigLoader,
) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-needs")

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(TaskStatus.FAILED, {})}
    )
    assert not ctx2.task.enable

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(TaskStatus.DISABLED, {})}
    )
    assert not ctx2.task.enable

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(TaskStatus.SUCCEEDED, {})}
    )
    assert ctx2.task.enable


async def test_pipeline_enable_success(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-enable")

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(TaskStatus.FAILED, {})}
    )
    assert not ctx2.task.enable

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(TaskStatus.DISABLED, {})}
    )
    assert not ctx2.task.enable

    ctx2 = await ctx.with_task(
        "task-2", needs={"task_a": DepCtx(TaskStatus.SUCCEEDED, {})}
    )
    assert ctx2.task.enable


async def test_pipeline_with_batch_action(batch_config_loader: ConfigLoader) -> None:
    ctx = await BatchContext.create(batch_config_loader, "batch-action-call")

    assert await ctx.is_action("test")
    ctx2 = await ctx.with_action("test", needs={})
    assert isinstance(ctx2, BatchActionContext)

    ctx3 = await ctx2.with_task("task_1", needs={})
    assert ctx3.task.id == "task_1"
    assert ctx3.task.full_id == ("test", "task_1")
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

    assert ctx3.graph == {
        ("test", "task_1"): set(),
        ("test", "task_2"): {("test", "task_1")},
    }
    assert ctx3.matrix == {}
    assert ctx3.strategy.max_parallel == 10
    assert ctx3.strategy.fail_fast
