import aiohttp
import asyncio
import datetime
import humanize
import logging
import time
from functools import wraps
from neuro_sdk import ClientError, JobStatus, ServerNotAvailable
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
)
from typing_extensions import Concatenate, ParamSpec, Protocol

from .types import COLORS, FullID, TaskStatus


def fmt_status(status: Union[JobStatus, TaskStatus]) -> str:
    if isinstance(status, JobStatus):
        status = TaskStatus(status)
    else:
        assert isinstance(status, TaskStatus)
    color = COLORS.get(status, "none")
    return f"[{color}]{status.value}[/{color}]"


def fmt_id(id: Union[str, FullID]) -> str:
    if isinstance(id, str):
        s_id = id
    else:
        s_id = ".".join(id)
    return f"[b]{s_id}[/b]"


def fmt_raw_id(raw_id: str) -> str:
    return f"[bright_black]{raw_id}[/bright_black]"


def fmt_datetime(when: Optional[datetime.datetime]) -> str:
    if when is None:
        return "N/A"
    delta = datetime.datetime.now(datetime.timezone.utc) - when
    if delta < datetime.timedelta(days=1):
        return cast(str, humanize.naturaltime(delta))
    else:
        return cast(str, humanize.naturaldate(when.astimezone()))


def fmt_timedelta(delta: datetime.timedelta) -> str:
    s = int(delta.total_seconds())
    if s < 0:
        raise ValueError(f"Invalid delta {delta}: expect non-negative total value")
    _sec_in_minute = 60
    _sec_in_hour = _sec_in_minute * 60
    _sec_in_day = _sec_in_hour * 24
    d, s = divmod(s, _sec_in_day)
    h, s = divmod(s, _sec_in_hour)
    m, s = divmod(s, _sec_in_minute)
    return "".join(
        [
            f"{d}d" if d else "",
            f"{h}h" if h else "",
            f"{m}m" if m else "",
            f"{s}s" if s else "",
        ]
    )


RUNNING_JOB_STATUSES = {JobStatus.PENDING, JobStatus.RUNNING}
RUNNING_TASK_STATUSES = {TaskStatus.PENDING, TaskStatus.RUNNING}

TERMINATED_JOB_STATUSES = {
    JobStatus.FAILED,
    JobStatus.SUCCEEDED,
    JobStatus.CANCELLED,
}

TERMINATED_TASK_STATUSES = {
    TaskStatus.FAILED,
    TaskStatus.SUCCEEDED,
    TaskStatus.CANCELLED,
}


JOB_TAG_PATTERN = r"\A[a-z](?:[-.:/]?[a-z0-9]){0,255}\Z"


async def run_subproc(exe: str, *args: str) -> None:
    proc = await asyncio.create_subprocess_exec(exe, *args)
    try:
        retcode = await proc.wait()
        if retcode:
            raise SystemExit(retcode)
    finally:
        if proc.returncode is None:
            # Kill neuro process if not finished
            # (e.g. if KeyboardInterrupt or cancellation was received)
            proc.kill()
            await proc.wait()


class GlobalOptions(Protocol):
    @property
    def verbosity(self) -> int:
        ...

    @property
    def show_traceback(self) -> bool:
        ...


def encode_global_options(options: GlobalOptions) -> List[str]:
    global_options = []
    verbosity_abs = abs(options.verbosity)
    if options.verbosity < 0:
        global_options += ["-q"] * verbosity_abs
    if options.verbosity > 0:
        global_options += ["-v"] * verbosity_abs
    if options.show_traceback:
        global_options += ["--show-traceback"]
    return global_options


class CommandRunner(Protocol):
    async def __call__(self, *args: str) -> None:
        ...


def make_cmd_exec(exe: str, *, global_options: Iterable[str] = ()) -> CommandRunner:
    async def _runner(*args: str) -> None:
        await run_subproc(exe, *global_options, *args)

    return _runner


log = logging.getLogger(__name__)


# Copied from neuro_sdk.utils to avoid dependency on private class
class retries:
    def __init__(
        self,
        msg: str,
        timeout: float = 60,
        delay: float = 0.1,
        factor: float = 1.5,
        cap: float = 5,
        exceptions: Sequence[Type[Exception]] = (),
        logger: Callable[[str], None] = log.info,
    ) -> None:
        self._msg = msg
        self._timeout = timeout
        self._delay = delay
        self._factor = factor
        self._cap = cap
        self._exceptions = (aiohttp.ClientError,) + tuple(exceptions)
        self._logger = logger
        self._done = False
        self.reset()

    def reset(self) -> None:
        self._t0 = time.monotonic()
        self._sleeptime = self._delay

    def __iter__(self) -> Iterator["retries"]:
        while not self._done:
            yield self

    async def __aenter__(self) -> None:
        pass

    async def __aexit__(
        self, type: Type[BaseException], value: BaseException, tb: Any
    ) -> bool:
        if type is None:
            # Stop iteration
            pass
        elif issubclass(type, self._exceptions):
            t1 = time.monotonic()
            if t1 - self._t0 <= self._timeout:
                self._logger(f"{self._msg}: {value}.  Retry...")
                await asyncio.sleep(self._sleeptime)
                self._sleeptime = min(self._sleeptime * self._factor, self._cap)
                return True
        self._done = True
        return False


F = TypeVar("F", bound=Callable[..., Any])


def async_retried(
    msg: str,
    *,
    timeout: float = 60,
    delay: float = 0.1,
    factor: float = 1.5,
    cap: float = 5,
    exceptions: Sequence[Type[Exception]] = (),
) -> Callable[[F], F]:
    def _deco(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            for retry in retries(
                msg,
                timeout=timeout,
                delay=delay,
                factor=factor,
                cap=cap,
                exceptions=exceptions,
            ):
                async with retry:
                    return await func(*args, **kwargs)

        return cast(F, wrapper)

    return _deco


class RetryConfig:
    def __init__(self) -> None:
        self._retry_timeout = 15 * 60
        self._delay = 15
        self._delay_factor = 1.5
        self._delay_cap = 60


_P = ParamSpec("_P")
_R = TypeVar("_R")


def retry(
    func: Callable[Concatenate[RetryConfig, _P], Awaitable[_R]]  # type: ignore
) -> Callable[Concatenate[RetryConfig, _P], Awaitable[_R]]:  # type: ignore
    async def inner(
        self: RetryConfig, *args: _P.args, **kwargs: _P.kwargs  # type: ignore
    ) -> _R:
        for retry in retries(
            f"{func!r}(*{args!r}, **{kwargs!r})",
            timeout=self._retry_timeout,
            delay=self._delay,
            factor=self._delay_factor,
            cap=self._delay_cap,
            exceptions=(ClientError, ServerNotAvailable, OSError),
        ):
            async with retry:
                return await func(self, *args, **kwargs)  # type: ignore
        assert False, "Unreachable"

    return inner
