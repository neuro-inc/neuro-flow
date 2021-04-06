import dataclasses

import abc
import collections
from abc import abstractmethod
from typing import (
    AbstractSet,
    Any,
    Callable,
    ForwardRef,
    Iterable,
    List,
    Optional,
    Type,
)

from neuro_flow.context import Context, InputsCtx, NeedsCtx, TagsCtx
from neuro_flow.expr import AttrGetter, EvalError, Expr, Item, ItemGetter, Lookup


def validate_expr(
    expr: Expr[Any],
    context: Type[Context],
    known_needs: AbstractSet[str] = frozenset(),
    known_inputs: AbstractSet[str] = frozenset(),
) -> List[EvalError]:
    errors: List[EvalError] = []
    for lookup in iter_lookups(expr):
        validate_lookup(lookup, context, errors.append, known_needs, known_inputs)
    return errors


def iter_lookups(expr: Expr[Any]) -> Iterable[Lookup]:
    def _iter_lookups(top_level_items: Iterable[Item]) -> Iterable[Lookup]:
        for item in top_level_items:
            if isinstance(item, Lookup):
                yield item
            yield from _iter_lookups(item.child_items())

    return _iter_lookups(getattr(expr, "_parsed", None) or [])


def _get_dataclass_field_type(dataclass: Any, attr: str) -> Optional[Any]:
    return {field.name: field.type for field in dataclasses.fields(dataclass)}.get(attr)


class GetterVisitor(abc.ABC):
    @abstractmethod
    def dataclass(self, obj: Any) -> Optional[Any]:
        pass

    @abstractmethod
    def mapping(self, obj: Any) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, obj: Any) -> Optional[Any]:
        pass


def _format_obj_name(obj: Any) -> str:
    if hasattr(obj, "__name__"):
        return str(obj.__name__)
    if obj == TagsCtx:
        return "TagsCtx"
    return str(obj)


class AttrGetterVisitor(GetterVisitor):
    def __init__(
        self,
        record_error: Callable[[EvalError], None],
        known_needs: AbstractSet[str],
        known_inputs: AbstractSet[str],
        getter: AttrGetter,
    ):
        self._record_error = record_error
        self._known_needs = known_needs
        self._known_inputs = known_inputs
        self._getter = getter

    def dataclass(self, obj: Any) -> Optional[Any]:
        new_ctx = _get_dataclass_field_type(obj, self._getter.name)
        if new_ctx is None:
            self._record_error(
                EvalError(
                    f"'{_format_obj_name(obj)}' has no attribute "
                    f"'{self._getter.name}'",
                    self._getter.start,
                    self._getter.end,
                )
            )
        return new_ctx

    def mapping(self, obj: Any) -> Optional[Any]:
        if obj == NeedsCtx and self._getter.name not in self._known_needs:
            self._record_error(
                EvalError(
                    f"Task '{self._getter.name}' is not available under "
                    f"needs context",
                    self._getter.start,
                    self._getter.end,
                )
            )
        if obj == InputsCtx and self._getter.name not in self._known_inputs:
            self._record_error(
                EvalError(
                    f"Input '{self._getter.name}' is undefined",
                    self._getter.start,
                    self._getter.end,
                )
            )
        return obj.__args__[1]

    def set(self, obj: Any) -> Optional[Any]:
        self._record_error(
            EvalError(
                f"'{_format_obj_name(obj)}' has no attribute " f"'{self._getter.name}'",
                self._getter.start,
                self._getter.end,
            )
        )
        return None


class ItemGetterVisitor(GetterVisitor):
    def __init__(self, record_error: Callable[[EvalError], None], getter: ItemGetter):
        self._record_error = record_error
        self._getter = getter

    def dataclass(self, obj: Any) -> Optional[Any]:
        self._record_error(
            EvalError(
                f"'{_format_obj_name(obj)}' is not subscriptable",
                self._getter.start,
                self._getter.end,
            )
        )
        return None

    def mapping(self, obj: Any) -> Optional[Any]:
        return obj.__args__[1]

    def set(self, obj: Any) -> Optional[Any]:
        self._record_error(
            EvalError(
                f"'{_format_obj_name(obj)}' is not subscriptable",
                self._getter.start,
                self._getter.end,
            )
        )
        return None


def _eval_forward_ref(ref: ForwardRef) -> Any:
    from neuro_flow import context

    return ref._evaluate(context.__dict__, {})


def validate_lookup(
    lookup: Lookup,
    context: Type[Context],
    record_error: Callable[[EvalError], None],
    known_needs: AbstractSet[str],
    known_inputs: AbstractSet[str],
) -> None:
    ctx = _get_dataclass_field_type(context, lookup.root)
    if ctx is None:
        record_error(
            EvalError(f"Unknown context '{lookup.root}'", lookup.start, lookup.end)
        )
        return
    for getter in lookup.trailer:
        if isinstance(ctx, ForwardRef):
            ctx = _eval_forward_ref(ctx)
        if isinstance(getter, AttrGetter):
            visitor: GetterVisitor = AttrGetterVisitor(
                record_error,
                known_needs,
                known_inputs,
                getter,
            )
        else:
            assert isinstance(getter, ItemGetter)
            visitor = ItemGetterVisitor(
                record_error,
                getter,
            )

        if dataclasses.is_dataclass(ctx):
            ctx = visitor.dataclass(ctx)
        elif hasattr(ctx, "__origin__"):  # This is type alias
            origin = ctx.__origin__
            if origin == collections.abc.Mapping:
                ctx = visitor.mapping(ctx)
            elif origin == collections.abc.Set:
                ctx = visitor.set(ctx)
        else:
            ctx = None  # Unknown ...Ctx type, skip check

        if ctx is None:
            return
