import asyncio
from neuromation.api import Client, Factory, JobDescription, JobStatus, ResourceNotFound
from types import TracebackType
from typing import AbstractSet, List, Optional, Tuple, Type
from typing_extensions import AsyncContextManager

from . import ast
from .context import BatchContext, ImageCtx, UnknownJob, VolumeCtx
from .parser import parse_batch
from .types import LocalPath


class BatchRunner(AsyncContextManager["BatchRunner"]):
    def __init__(self, workspace: LocalPath, config_file: LocalPath) -> None:
        self._workspace = workspace
        self._config_file = config_file
        self._ctx: Optional[BatchContext] = None

    async def post_init(self) -> None:
        if self._ctx is not None:
            return
        flow = parse_batch(self._workspace, self._config_file)
        self._ctx = await BatchContext.create(flow)

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "BatchRunner":
        await self.post_init()
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    @property
    def ctx(self) -> BatchContext:
        assert self._ctx is not None
        return self._ctx

    async def run_subproc(self, exe: str, *args: str) -> None:
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

    async def bake(self, batch: str) -> None:
        # burn is another option
        if not exists():
            init()
        else:
            checkpoints = read_checkpoints()
            for ch in checkpoints:
                if await get_status(ch.raw_id) in (
                    JobStatus.SUCCEEDED,
                    JobStatus.FAILED,
                ):
                    self.process_result(ch.raw_id)

    async def start_task(self, task_ctx) -> None:
        pass
