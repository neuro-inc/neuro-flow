import asyncio
from neuromation.api import Client, Factory, JobDescription, JobStatus, ResourceNotFound
from types import TracebackType
from typing import AbstractSet, List, Optional, Tuple, Type
from typing_extensions import AsyncContextManager

from . import ast
from .context import BatchContext, ImageCtx, UnknownJob, VolumeCtx
from .parser import ConfigDir, parse_batch
from .storage import BatchStorage
from .types import LocalPath


class BatchRunner(AsyncContextManager["BatchRunner"]):
    def __init__(self, config_dir: ConfigDir, storage: BatchStorage) -> None:
        self._config_dir = config_dir
        self._storage = storage

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "BatchRunner":
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

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

    async def bake(self, batch_name: str) -> None:
        # batch_name is a name of yaml config inside self._workspace / .neuro
        # folder without the file extension
        config_file = (self._config_dir.config_dir / (batch_name + ".yml")).resolve()

        # Check that the yaml is parseable
        flow = parse_batch(self._config_dir.workspace, config_file)
        ctx = await BatchContext.create(flow)
        for volume in ctx.volumes.values():
            if volume.local is not None:
                # TODO: sync volumes if needed
                pass

        config_content = config_file.read_text()

        bake_id = await self._storage.create_bake(batch_name, config_content)
        # TODO: run this function in a job
        await self.process(bake_id)

    async def process(self, bake_id: str) -> None:
        attempt = await self._storage.find_last_attempt(bake_id)

        # bake_id is a string used for
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
