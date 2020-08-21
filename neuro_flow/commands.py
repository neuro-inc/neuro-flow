# Workflow commands that can be used in job's output
# Candidates:
# ::set-env::
# ::set-output::
# ::save-state::

import logging
import re
from types import TracebackType
from typing import (
    AsyncContextManager,
    AsyncIterator,
    Dict,
    List,
    Mapping,
    Optional,
    Tuple,
    Type,
)


log = logging.getLogger(__name__)


def _compile(commands: List[Tuple[str, str]]) -> Dict[str, "re.Pattern[bytes]"]:
    ret = {}
    for cmd, regexp in commands:
        cmd2 = cmd.replace("-", "_")
        if regexp:
            inner = r"\s+" + regexp
        else:
            inner = ""
        ret[cmd2] = re.compile(
            rf"\A\s*::\s*{cmd}{inner}\s*::(?P<value>.+)\Z".encode("ascii")
        )
    return ret


class CmdProcessor(AsyncContextManager["CmdProcessor"]):
    COMMANDS = [
        ("set-output", r"name\s*=\s*(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"),
        ("save-state", r"name\s*=\s*(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"),
        ("stop-commands", ""),
    ]

    COMMANDS_RE = _compile(COMMANDS)

    def __init__(self) -> None:
        self._buf = bytearray()
        self._outputs: Dict[str, str] = {}
        self._states: Dict[str, str] = {}
        self._stop_commands: Optional[bytes] = None

    @property
    def outputs(self) -> Mapping[str, str]:
        return self._outputs

    @property
    def states(self) -> Mapping[str, str]:
        return self._states

    async def __aenter__(self) -> "CmdProcessor":
        return self

    async def __aexit__(
        self,
        exc_tp: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        assert not self._buf, "Missed call feed_eof()"

    async def feed_chunk(self, chunk: bytes) -> AsyncIterator[bytes]:
        self._buf.extend(chunk)
        if b"\n" in self._buf:
            lines = self._buf.splitlines(keepends=True)
            self._buf = lines.pop(-1)
            for line in lines:
                ret = await self.feed_line(line)
                if ret is not None:
                    yield ret

    async def feed_eof(self) -> AsyncIterator[bytes]:
        ret = await self.feed_line(self._buf)
        if ret is not None:
            yield ret
        self._buf = bytearray()

    async def feed_line(self, origin_line: bytes) -> Optional[bytes]:
        line = origin_line.strip()
        if not line.startswith(b"::"):
            return origin_line
        if self._stop_commands is not None:
            if self._stop_commands == line:
                self._stop_commands = None
                return None
            else:
                return origin_line
        for cmd, pattern in self.COMMANDS_RE.items():
            match = pattern.match(line)
            if match is None:
                continue
            handler = getattr(self.__class__, cmd)
            await handler(self, match)
            return None
        else:
            log.warning("Unknown command %r", line.decode("utf-8", "replace"))
        return None

    async def set_output(self, match: "re.Match[bytes]") -> None:
        name = match.group("name").decode("utf-8", "replace")
        value = match.group("value").decode("utf-8", "replace")
        self._outputs[name] = value

    async def save_state(self, match: "re.Match[bytes]") -> None:
        name = match.group("name").decode("utf-8", "replace")
        value = match.group("value").decode("utf-8", "replace")
        self._states[name] = value

    async def stop_commands(self, match: "re.Match[bytes]") -> None:
        value = match.group("value")
        self._stop_commands = b"::" + value + b"::"


def _check_commands() -> None:
    for cmd, _ in CmdProcessor.COMMANDS:
        handler = getattr(CmdProcessor, cmd.replace("-", "_"), None)
        assert handler is not None, f"Command {cmd} has no handler"


_check_commands()
del _check_commands
del _compile
