import click
import functools
from asyncio import iscoroutinefunction
from click.types import convert_type
from neuromation.cli.asyncio_utils import Runner
from typing import Any, Awaitable, Callable, TypeVar


_T = TypeVar("_T")


def wrap_async(
    pass_obj: bool = True,
) -> Callable[[Callable[..., Awaitable[_T]]], Callable[..., _T]]:
    def _decorator(callback: Callable[..., Awaitable[_T]]) -> Callable[..., _T]:
        assert iscoroutinefunction(callback)

        @functools.wraps(callback)
        def wrapper(*args: Any, **kwargs: Any) -> _T:
            with Runner() as runner:
                return runner.run(callback(*args, **kwargs))

        if pass_obj:
            wrapper = click.pass_obj(wrapper)

        return wrapper

    return _decorator


def option(*param_decls: Any, **attrs: Any) -> Callable[..., Any]:
    option_attrs = attrs.copy()
    typ = convert_type(attrs.get("type"), attrs.get("default"))
    autocompletion = getattr(typ, "complete", None)
    option_attrs.setdefault("autocompletion", autocompletion)
    return click.option(*param_decls, **option_attrs)


def argument(*param_decls: Any, **attrs: Any) -> Callable[..., Any]:
    arg_attrs = attrs.copy()
    typ = convert_type(attrs.get("type"), attrs.get("default"))
    autocompletion = getattr(typ, "complete", None)
    arg_attrs.setdefault("autocompletion", autocompletion)
    return click.argument(*param_decls, **arg_attrs)
