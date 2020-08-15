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


def _compile(commands: List[Tuple[str, str]]) -> Dict[str, "re.Pattern[str]"]:
    ret = {}
    for cmd, regexp in commands:
        cmd2 = cmd.replace("-", "_")
        if regexp:
            inner = r"\s+" + regexp
        else:
            inner = ""
        ret[cmd2] = re.compile(rf"\A\s*::\s*{cmd}{inner}\s*::(?P<value>.+)\Z")
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
        self._stop_commands: Optional[str] = None

    @property
    def outputs(self) -> Mapping[str, str]:
        return self._outputs

    @property
    def envs(self) -> Mapping[str, str]:
        return self._envs

    @property
    def states(self) -> Mapping[str, str]:
        return self._states

    async def __aenter__(self) -> "CmdProcessor":
        return self

    async def __aexit__(
        self,
        exc_tp: Optional[Type[Exception]],
        exc_val: Optional[Exception],
        exc_tb: Optional[TracebackType],
    ) -> None:
        line = self._buf.decode("utf-8", "replace")
        await self.feed_line(line)

    async def feed_chunk(self, chunk: bytes) -> None:
        self._buf.extend(chunk)
        if b"\n" in self._buf:
            blines = self._buf.splitlines(keepends=True)
            self._buf = blines.pop(-1)
            for bline in blines:
                line = bline.decode("utf-8", "replace")
                await self.feed_line(line)

    async def feed_line(self, line: str) -> None:
        line = line.strip()
        if not line.startswith("::"):
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
            log.warning("Unknown command %r", line)

    async def set_output(self, match: re.Match) -> None:
        name = match.group("name")
        value = match.group("value")
        self._outputs[name] = value

    async def save_state(self, match: re.Match) -> None:
        name = match.group("name")
        value = match.group("value")
        self._states[name] = value

    async def stop_commands(self, match: re.Match) -> None:
        value = match.group("value")
        self._stop_commands = "::" + value + "::"


def _check_commands():
    for cmd, _ in CmdProcessor.COMMANDS:
        handler = getattr(CmdProcessor, cmd.replace("-", "_"), None)
        assert handler is not None, f"Command {cmd} has no handler"


_check_commands()
del _check_commands
