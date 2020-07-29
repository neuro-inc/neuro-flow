import asyncio
import tempfile
from neuromation.api import Client, JobStatus
from types import TracebackType
from typing import AsyncIterator, Dict, Iterable, Optional, Type
from typing_extensions import AsyncContextManager

from . import ast
from .context import BatchContext
from .parser import ConfigDir, parse_batch
from .storage import BatchStorage, FinishedTask, StartedTask, TaskResult
from .types import LocalPath


class BatchRunner(AsyncContextManager["BatchRunner"]):
    def __init__(
        self, config_dir: ConfigDir, client: Client, storage: BatchStorage
    ) -> None:
        self._config_dir = config_dir
        self._client = client
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
        assert isinstance(flow, ast.BatchFlow)

        ctx = await BatchContext.create(flow)
        for volume in ctx.volumes.values():
            if volume.local is not None:
                # TODO: sync volumes if needed
                pass

        config_content = config_file.read_text()

        bake_id = await self._storage.create_bake(
            batch_name, config_file.name, config_content
        )
        await self._storage.create_attempt(bake_id, 1, ctx.cardinality)
        # TODO: run this function in a job
        await self.process(bake_id)

    async def process(self, bake_id: str) -> None:
        config_dir = LocalPath(tempfile.mkdtemp(prefix=bake_id))
        bake_init = await self._storage.fetch_bake_init(bake_id)
        config_content = await self._storage.fetch_config(bake_init.config_file.name)
        config_file = config_dir / bake_init.config_file.name
        config_file.write_text(config_content)

        flow = parse_batch(None, config_file)
        assert isinstance(flow, ast.BatchFlow)

        ctx = await BatchContext.create(flow)

        attempt = await self._storage.find_last_attempt(bake_id)
        finished, started = await self._storage.fetch_attempt(
            bake_id, attempt, ctx.cardinality
        )
        while True:
            for t1 in started.values():
                if t1.id in finished:
                    continue
                status = await self._client.jobs.status(t1.raw_id)
                if status.status in (JobStatus.FAILED, JobStatus.SUCCEEDED):
                    finished[t1.id] = await self._storage.finish_task(
                        bake_id,
                        attempt,
                        len(started) + len(finished),
                        ctx.cardinality,
                        t1,
                        status,
                    )

            if len(finished) == ctx.cardinality:
                self._storage.finish_attempt(bake_id, self.accumulate_result(finished))
                return

            async for task_ctx in self.ready_to_start(ctx, started, finished):
                t2 = await self.start_task(task_ctx)
                finished[t2.id] = t2

            await asyncio.sleep(3)

    def accumulate_result(self, finished: Iterable[FinishedTask]) -> TaskResult:
        # TODO: handle cancelled tasks
        for task in finished:
            if task.status == JobStatus.FAILED:
                return TaskResult.FAILURE
        else:
            return TaskResult.SUCCESS

    async def ready_to_start(
        self,
        ctx: BatchContext,
        started: Dict[str, StartedTask],
        finished: Dict[str, FinishedTask],
    ) -> AsyncIterator[BatchContext]:
        pass

    async def start_task(self, task_ctx: BatchContext) -> None:
        pass
