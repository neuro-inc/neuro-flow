# Workflow commands that can be used in job's output
# Candidates:
# ::set-env::
# ::set-output::
# ::save-state::

from types import TracebackType
from typing import AsyncContextManager, Dict, Optional, Type


class CmdProcessor(AsyncContextManager["CmdProcessor"]):
    def __init__(self) -> None:
        self._buf = bytearray()
        self._outputs: Dict[str, str] = {}

    @property
    def outputs(self) -> Dict[str, str]:
        return self._outputs

    async def __aenter__(self) -> "CmdProcessor":
        return self

    async def __exit__(
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
        pass
