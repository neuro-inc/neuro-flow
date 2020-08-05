# Workflow commands that can be used in job's output
# Candidates:
# ::set-env::
# ::set-output::
# ::save-state::

from typing import AsyncContextManager


class CmdProcessor(AsyncContextManager["CmdProcessor"]):
    def __init__(self) -> None:
        pass

    async def feed(self, line: str) -> None:
        pass
