from neuro_flow.context import BatchActionContext, BatchContext, BatchTaskContext
from neuro_flow.expr import StrExpr
from neuro_flow.expr_validation import validate_expr
from neuro_flow.tokenizer import Pos
from neuro_flow.types import LocalPath


def test_expr_validation_ok() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ flow.flow_id }}",
    )
    errors = validate_expr(expr, BatchContext)
    assert errors == []


def test_expr_validation_unknown_context() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ something_new }}",
    )
    errors = validate_expr(expr, BatchContext)
    assert errors[0].args[0] == "Unknown context 'something_new'"


def test_expr_validation_not_context_field() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ flow.foo }}",
    )
    errors = validate_expr(expr, BatchContext)
    assert errors[0].args[0] == "'BatchFlowCtx' has no attribute 'foo'"


def test_expr_validation_invalid_need() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ needs.fff }}",
    )
    errors = validate_expr(expr, BatchTaskContext, known_needs=set())
    assert errors[0].args[0] == "Task 'fff' is not available under needs context"


def test_expr_validation_invalid_input() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ inputs.fff }}",
    )
    errors = validate_expr(expr, BatchActionContext, known_inputs=set())
    assert errors[0].args[0] == "Input 'fff' is undefined"


def test_expr_validation_bad_subcontext_lookup() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ needs.task.foo }}",
    )
    errors = validate_expr(expr, BatchTaskContext, known_needs={"task"})
    assert errors[0].args[0] == "'DepCtx' has no attribute 'foo'"


def test_expr_validation_bad_set_attr() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ tags.anything }}",
    )
    errors = validate_expr(expr, BatchContext)
    assert errors[0].args[0] == "'TagsCtx' has no attribute 'anything'"


def test_expr_validation_bad_indexing() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ flow['flow_id'] }}",
    )
    errors = validate_expr(expr, BatchContext)
    assert errors[0].args[0] == "'BatchFlowCtx' is not subscriptable"


def test_expr_validation_set_indexing() -> None:
    expr = StrExpr(
        Pos(0, 0, LocalPath("<default>")),
        Pos(0, 0, LocalPath("<default>")),
        pattern="${{ tags['flow_id'] }}",
    )
    errors = validate_expr(expr, BatchContext)
    assert errors[0].args[0] == "'TagsCtx' is not subscriptable"
