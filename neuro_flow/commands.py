# Workflow commands that can be used in job's output
# Candidates:
# ::set-env::
# ::set-output::
# ::save-state::

import logging
import re
from types import TracebackType
from typing import AsyncContextManager, Dict, List, Mapping, Optional, Tuple, Type


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
        await self.feed_line(self._buf)

    async def feed_chunk(self, chunk: bytes) -> None:
        self._buf.extend(chunk)
        if b"\n" in self._buf:
            lines = self._buf.splitlines(keepends=True)
            self._buf = lines.pop(-1)
            for line in lines:
                await self.feed_line(line)

    async def feed_line(self, line: bytes) -> None:
        line = line.strip()
        if not line.startswith(b"::"):
            return
        if self._stop_commands is not None:
            if self._stop_commands == line:
                self._stop_commands = None
            return
        for cmd, pattern in self.COMMANDS_RE.items():
            match = pattern.match(line)
            if match is None:
                continue
            handler = getattr(self.__class__, cmd)
            await handler(self, match)
            return
        else:
            log.warning("Unknown command %r", line.decode("utf-8", "replace"))

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
