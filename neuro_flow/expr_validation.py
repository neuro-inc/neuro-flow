import dataclasses

import abc
import collections
import sys
from abc import abstractmethod
from typing import AbstractSet, Any, Callable, Iterable, List, Optional, Tuple, Type

from neuro_flow.context import Context, TagsCtx
from neuro_flow.expr import AttrGetter, EvalError, Expr, Item, ItemGetter, Lookup


if sys.version_info[:3] >= (3, 7):
    from typing_extensions import get_type_hints as _get_hints

    def get_hints(obj: Any) -> Any:
        return _get_hints(obj, include_extras=True)


else:
    from typing import get_type_hints as get_hints


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
    return get_hints(dataclass).get(attr)


class GetterVisitor(abc.ABC):
    @abstractmethod
    def dataclass(self, obj: Any) -> Optional[Any]:
        pass

    @abstractmethod
    def mapping(self, type_args: Tuple[Any, ...], metadata: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, type_args: Tuple[Any, ...], metadata: str) -> Optional[Any]:
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

    def mapping(self, type_args: Tuple[Any, ...], metadata: str) -> Optional[Any]:
        if metadata == "NeedsCtx" and self._getter.name not in self._known_needs:
            self._record_error(
                EvalError(
                    f"Task '{self._getter.name}' is not available under "
                    f"needs context",
                    self._getter.start,
                    self._getter.end,
                )
            )
        if metadata == "InputsCtx" and self._getter.name not in self._known_inputs:
            self._record_error(
                EvalError(
                    f"Input '{self._getter.name}' is undefined",
                    self._getter.start,
                    self._getter.end,
                )
            )
        return type_args[1]

    def set(self, type_args: Tuple[Any, ...], metadata: str) -> Optional[Any]:
        self._record_error(
            EvalError(
                f"'{metadata}' has no attribute " f"'{self._getter.name}'",
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

    def mapping(self, type_args: Tuple[Any, ...], metadata: str) -> Optional[Any]:
        return type_args[1]

    def set(self, type_args: Tuple[Any, ...], metadata: str) -> Optional[Any]:
        self._record_error(
            EvalError(
                f"'{metadata}' is not subscriptable",
                self._getter.start,
                self._getter.end,
            )
        )
        return None


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
        elif hasattr(ctx, "__metadata__"):  # This is typing.Annotated
            # The following code is ugly, unfortunately typing got
            # clear retrospection api only recently,
            # and it is not backported to python3.6
            annotation = ctx.__metadata__[0]
            origin_type = ctx.__args__[0]
            type_args = origin_type.__args__
            if hasattr(origin_type, "__extra__"):
                # python 3.6
                origin_abc = origin_type.__extra__
            else:
                origin_abc = origin_type.__origin__

            if origin_abc == collections.abc.Mapping:
                ctx = visitor.mapping(type_args, annotation)
            elif origin_abc == collections.abc.Set:
                ctx = visitor.set(type_args, annotation)
        else:
            ctx = None  # Unknown ...Ctx type, skip check

        if ctx is None:
            return
