import click
import datetime
import functools
import sys
from asyncio import iscoroutinefunction
from click.types import convert_type
from contextlib import contextmanager
from neuro_cli.asyncio_utils import Runner
from neuro_sdk import ResourceNotFound
from typing import Any, Awaitable, Callable, Iterator, TypeVar

from neuro_flow.storage import Storage


@contextmanager
def _runner() -> Iterator[Runner]:
    # Suppress prints unhandled exceptions
    # on event loop closing to overcome aiohttp bug
    # Check https://github.com/aio-libs/aiohttp/issues/4324
    try:
        with Runner() as runner:
            yield runner
            sys.stderr = None  # type: ignore
    finally:
        sys.stderr = sys.__stderr__


_T = TypeVar("_T")


def wrap_async(
    pass_obj: bool = True,
) -> Callable[[Callable[..., Awaitable[_T]]], Callable[..., _T]]:
    def _decorator(callback: Callable[..., Awaitable[_T]]) -> Callable[..., _T]:
        assert iscoroutinefunction(callback)

        @functools.wraps(callback)
        def wrapper(*args: Any, **kwargs: Any) -> _T:
            with _runner() as runner:
                return runner.run(callback(*args, **kwargs))

        if pass_obj:
            wrapper = click.pass_obj(wrapper)  # type: ignore

        return wrapper

    return _decorator


def option(*param_decls: Any, **attrs: Any) -> Callable[..., Any]:
    option_attrs = attrs.copy()
    typ = convert_type(attrs.get("type"), attrs.get("default"))
    autocompletion = getattr(typ, "complete", None)
    option_attrs.setdefault("autocompletion", autocompletion)
    return click.option(*param_decls, **option_attrs)  # type: ignore


def argument(*param_decls: Any, **attrs: Any) -> Callable[..., Any]:
    arg_attrs = attrs.copy()
    typ = convert_type(attrs.get("type"), attrs.get("default"))
    autocompletion = getattr(typ, "complete", None)
    arg_attrs.setdefault("autocompletion", autocompletion)
    return click.argument(*param_decls, **arg_attrs)  # type: ignore


BAKE_ID_PATTERN = r"job-[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12}"


def _is_bake_id_maybe(id_or_name: str) -> bool:
    try:
        batch, whenstr, suffix = id_or_name.split("_")
        datetime.datetime.fromisoformat(whenstr)
        return len(suffix) == 6
    except ValueError:
        return False


async def resolve_bake(id_or_name: str, *, project: str, storage: Storage) -> str:
    if _is_bake_id_maybe(id_or_name):
        return id_or_name
    try:
        bake = await storage.fetch_bake_by_name(project, id_or_name)
        return bake.bake_id
    except ResourceNotFound:
        return id_or_name
