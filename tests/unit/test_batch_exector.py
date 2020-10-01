from dataclasses import replace

import asyncio
import pytest
from datetime import datetime
from neuromation.api import (
    Client,
    Container,
    JobDescription,
    JobRestartPolicy,
    JobStatus,
    JobStatusHistory,
    ResourceNotFound,
    get as api_get,
)
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import AsyncIterator, Awaitable, Callable, Dict, Optional, Sequence, cast
from yarl import URL

from neuro_flow.batch_executor import BatchExecutor, ExecutorData
from neuro_flow.batch_runner import BatchRunner
from neuro_flow.parser import ConfigDir
from neuro_flow.storage import BatchFSStorage, BatchStorage, LocalFS


class JobsMock:
    # Mock for client.jobs subsystem

    _data: Dict[str, JobDescription]
    _outputs: Dict[str, bytes]

    def __init__(self) -> None:
        self.id_counter = 0
        self._data = {}
        self._outputs = {}

    def _make_next_id(self) -> int:
        self.id_counter += 1
        return self.id_counter

    # Method for controlling in tests

    async def _get_task(self, task_name: str) -> JobDescription:
        while True:
            for descr in self._data.values():
                if f"task:{task_name}" in descr.tags:
                    return descr
            await asyncio.sleep(0.01)

    async def get_task(self, task_name: str, timeout: float = 1) -> JobDescription:
        try:
            return await asyncio.wait_for(self._get_task(task_name), timeout=timeout)
        except asyncio.TimeoutError:
            raise AssertionError(
                f'Task "{task_name}" did not appeared in timeout of {timeout}'
            )

    async def mark_started(self, task_name: str) -> None:
        descr = await self.get_task(task_name)
        if descr.status == JobStatus.PENDING:
            descr = replace(descr, status=JobStatus.RUNNING)
            new_history = replace(
                descr.history, status=JobStatus.RUNNING, started_at=datetime.now()
            )
            descr = replace(descr, history=new_history)
            self._data[descr.id] = descr

    async def mark_done(self, task_name: str, output: bytes = b"") -> None:
        await self.mark_started(task_name)
        descr = await self.get_task(task_name)
        if descr.status == JobStatus.RUNNING:
            descr = replace(descr, status=JobStatus.SUCCEEDED)
            new_history = replace(
                descr.history,
                status=JobStatus.SUCCEEDED,
                finished_at=datetime.now(),
                exit_code=0,
            )
            descr = replace(descr, history=new_history)
            self._data[descr.id] = descr
        self._outputs[descr.id] = output

    # Fake Jobs methods

    async def run(
        self,
        container: Container,
        *,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
        description: Optional[str] = None,
        is_preemptible: bool = False,
        schedule_timeout: Optional[float] = None,
        restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER,
        life_span: Optional[float] = None,
    ) -> JobDescription:
        job_id = f"job-{self._make_next_id()}"
        self._data[job_id] = JobDescription(
            id=job_id,
            owner="test-user",
            cluster_name="default",
            status=JobStatus.PENDING,
            history=JobStatusHistory(
                status=JobStatus.PENDING,
                reason="",
                description="",
                created_at=datetime.now(),
            ),
            container=container,
            is_preemptible=is_preemptible,
            uri=URL(f"job://default/test-user/{job_id}"),
            name=name,
            tags=tags,
            description=description,
            restart_policy=restart_policy,
            life_span=life_span,
        )
        return self._data[job_id]

    async def status(self, job_id: str) -> JobDescription:
        try:
            return self._data[job_id]
        except KeyError:
            raise ResourceNotFound

    async def monitor(self, job_id: str) -> AsyncIterator[bytes]:
        yield self._outputs.get(job_id, b"")


@pytest.fixture()  # type: ignore
def batch_storage(loop: None) -> BatchStorage:
    with TemporaryDirectory() as tmpdir:
        fs = LocalFS(Path(tmpdir))
        yield BatchFSStorage(fs)


@pytest.fixture()  # type: ignore
def prepare_executor_data(
    batch_storage: BatchStorage,
) -> Callable[[Path, str], Awaitable[ExecutorData]]:
    async def _prepare(config_loc: Path, batch_name: str) -> ExecutorData:
        config_dir = ConfigDir(
            workspace=config_loc,
            config_dir=config_loc,
        )
        # BatchRunner should not use client in this case
        return await BatchRunner(
            config_dir, cast(Client, None), batch_storage
        ).prepare_executor_data(batch_name)

    return _prepare


@pytest.fixture()  # type: ignore
def jobs_mock() -> JobsMock:
    return JobsMock()


@pytest.fixture()  # type: ignore
async def patched_client(jobs_mock: JobsMock) -> AsyncIterator[Client]:
    async with api_get() as client:
        client._jobs = jobs_mock
        yield client


@pytest.fixture()  # type: ignore
def start_executor(
    batch_storage: BatchStorage, patched_client: Client
) -> Callable[[ExecutorData], Awaitable[None]]:
    async def start(data: ExecutorData) -> None:
        await BatchExecutor(
            data, patched_client, batch_storage, pooling_timeout=0.01
        ).run()

    return start


@pytest.fixture()  # type: ignore
def run_executor(
    prepare_executor_data: Callable[[Path, str], Awaitable[ExecutorData]],
    start_executor: Callable[[ExecutorData], Awaitable[None]],
) -> Callable[[Path, str], Awaitable[None]]:
    async def run(config_loc: Path, batch_name: str) -> None:
        data = await prepare_executor_data(config_loc, batch_name)
        await start_executor(data)

    return run


async def test_simple_batch_ok(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.create_task(run_executor(assets, "batch-seq"))
    task_descr = await jobs_mock.get_task("task-1")
    assert task_descr.container.image.name == "ubuntu"
    assert task_descr.container.command
    assert "echo abc" in task_descr.container.command
    await jobs_mock.mark_done("task-1")

    task_descr = await jobs_mock.get_task("task-2")
    assert task_descr.container.image.name == "ubuntu"
    assert task_descr.container.command
    assert "echo def" in task_descr.container.command
    await jobs_mock.mark_done("task-2")
    await executor_task


async def test_batch_with_action_ok(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.create_task(run_executor(assets, "batch-action-call"))
    await jobs_mock.get_task("test.task-1")
    await jobs_mock.mark_done("test.task-1", "::set-output name=task1::Task 1 val 1".encode())

    await jobs_mock.get_task("test.task-2")
    await jobs_mock.mark_done("test.task-2", "::set-output name=task2::Task 2 value 2".encode())
    await executor_task
