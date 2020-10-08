from dataclasses import replace

import asyncio
import pytest
import shutil
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
from typing import (
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    cast,
)
from yarl import URL

from neuro_flow.batch_executor import BatchExecutor, ExecutorData, LocalsBatchExecutor
from neuro_flow.batch_runner import BatchRunner
from neuro_flow.parser import ConfigDir
from neuro_flow.storage import Bake, BatchFSStorage, BatchStorage, LocalFS
from neuro_flow.types import LocalPath


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

    async def mark_failed(self, task_name: str, output: bytes = b"") -> None:
        await self.mark_started(task_name)
        descr = await self.get_task(task_name)
        if descr.status == JobStatus.RUNNING:
            descr = replace(descr, status=JobStatus.FAILED)
            new_history = replace(
                descr.history,
                status=JobStatus.FAILED,
                finished_at=datetime.now(),
                exit_code=255,
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

    async def kill(self, job_id: str) -> None:
        descr = self._data[job_id]
        descr = replace(descr, status=JobStatus.CANCELLED)
        new_history = replace(
            descr.history,
            status=JobStatus.CANCELLED,
            started_at=descr.history.started_at or datetime.now(),
            finished_at=datetime.now(),
            exit_code=0,
        )
        descr = replace(descr, history=new_history)
        self._data[descr.id] = descr

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
def setup_exc_data(
    batch_storage: BatchStorage,
) -> Callable[[Path, str], Awaitable[ExecutorData]]:
    async def _prepare(config_loc: Path, batch_name: str) -> ExecutorData:
        config_dir = ConfigDir(
            workspace=config_loc,
            config_dir=config_loc,
        )
        # BatchRunner should not use client in this case
        async with BatchRunner(config_dir, cast(Client, None), batch_storage) as runner:
            return await runner._setup_exc_data(batch_name)

    return _prepare


@pytest.fixture()  # type: ignore
def cancel_batch(
    batch_storage: BatchStorage,
) -> Callable[[Path, str], Awaitable[None]]:
    async def _prepare(config_loc: Path, bake_id: str) -> None:
        config_dir = ConfigDir(
            workspace=config_loc,
            config_dir=config_loc,
        )
        async with BatchRunner(config_dir, cast(Client, None), batch_storage) as runner:
            await runner.cancel(bake_id)

    return _prepare


@pytest.fixture()  # type: ignore
def jobs_mock() -> JobsMock:
    return JobsMock()


@pytest.fixture()  # type: ignore
async def patched_client(
    api_config: Path, jobs_mock: JobsMock
) -> AsyncIterator[Client]:
    async with api_get(path=api_config) as client:
        client._jobs = jobs_mock
        yield client


@pytest.fixture()  # type: ignore
def start_locals_executor(
    batch_storage: BatchStorage, patched_client: Client
) -> Callable[[ExecutorData], Awaitable[None]]:
    async def start(data: ExecutorData) -> None:
        executor = await LocalsBatchExecutor.create(data, patched_client, batch_storage)
        await executor.run()

    return start


@pytest.fixture()  # type: ignore
def start_executor(
    batch_storage: BatchStorage, patched_client: Client
) -> Callable[[ExecutorData], Awaitable[None]]:
    async def start(data: ExecutorData) -> None:
        executor = await BatchExecutor.create(
            data, patched_client, batch_storage, polling_timeout=0.01
        )
        await executor.run()

    return start


@pytest.fixture()  # type: ignore
def run_executor(
    setup_exc_data: Callable[[Path, str], Awaitable[ExecutorData]],
    start_locals_executor: Callable[[ExecutorData], Awaitable[None]],
    start_executor: Callable[[ExecutorData], Awaitable[None]],
) -> Callable[[Path, str], Awaitable[None]]:
    async def run(config_loc: Path, batch_name: str) -> None:
        data = await setup_exc_data(config_loc, batch_name)
        await start_locals_executor(data)
        await start_executor(data)

    return run


def _executor_data_to_bake_id(data: ExecutorData) -> str:
    return Bake(
        project=data.project,
        batch=data.batch,
        when=data.when,
        suffix=data.suffix,
        graphs={},  # not needed for bake_id calculation
    ).bake_id


async def test_simple_batch_ok(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-seq"))
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
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-action-call"))
    await jobs_mock.get_task("test.task-1")
    await jobs_mock.mark_done(
        "test.task-1", "::set-output name=task1::Task 1 val 1".encode()
    )

    await jobs_mock.get_task("test.task-2")
    await jobs_mock.mark_done(
        "test.task-2", "::set-output name=task2::Task 2 value 2".encode()
    )
    await executor_task


@pytest.mark.parametrize(  # type: ignore
    "batch_name,vars",
    [
        ("batch-matrix-1", [("o1", "t1"), ("o1", "t2"), ("o2", "t1"), ("o2", "t2")]),
        ("batch-matrix-2", [("o1", "t2"), ("o2", "t1"), ("o2", "t2")]),
        (
            "batch-matrix-3",
            [("o1", "t1"), ("o1", "t2"), ("o2", "t1"), ("o2", "t2"), ("o3", "t3")],
        ),
        ("batch-matrix-4", [("o2", "t1"), ("o2", "t2"), ("o3", "t3")]),
    ],
)
async def test_batch_matrix(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
    batch_name: str,
    vars: List[Tuple[str, str]],
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, batch_name))
    for var_1, var_2 in vars:
        descr = await jobs_mock.get_task(f"task-1-{var_1}-{var_2}")
        assert descr.container.command
        assert f"{var_1}-{var_2}" in descr.container.command
        await jobs_mock.mark_done(f"task-1-{var_1}-{var_2}")

    await executor_task


@pytest.mark.parametrize(  # type: ignore
    "batch_name,max_parallel,vars",
    [
        pytest.param(
            "batch-matrix-max-parallel",
            2,
            [("o1", "t1"), ("o1", "t2"), ("o2", "t1"), ("o2", "t2")],
            marks=pytest.mark.xfail(reason="Local max_parallel is broken"),
        ),
        (
            "batch-matrix-max-parallel-global",
            2,
            [("o1", "t1"), ("o1", "t2"), ("o2", "t1"), ("o2", "t2")],
        ),
    ],
)
async def test_batch_matrix_max_parallel(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
    batch_name: str,
    max_parallel: int,
    vars: List[Tuple[str, str]],
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, batch_name))
    done, pending = await asyncio.wait(
        [jobs_mock.get_task(f"task-1-{var_1}-{var_2}") for var_1, var_2 in vars],
        return_when=asyncio.ALL_COMPLETED,
    )

    alive_cnt = sum(1 for task in done if task.exception() is None)
    assert alive_cnt == max_parallel
    executor_task.cancel()


async def test_enable_cancels_depending_tasks(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    await asyncio.wait_for(run_executor(assets, "batch-first-disabled"), timeout=1)


async def test_disabled_task_is_not_required(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets, "batch-disabled-not-needed")
    )

    await jobs_mock.mark_done("task-1")
    await jobs_mock.mark_done("task-3")
    await jobs_mock.mark_done("task-4")

    await executor_task


async def test_cancellation(
    jobs_mock: JobsMock,
    assets: Path,
    setup_exc_data: Callable[[Path, str], Awaitable[ExecutorData]],
    start_executor: Callable[[ExecutorData], Awaitable[None]],
    cancel_batch: Callable[[Path, str], Awaitable[ExecutorData]],
) -> None:
    data = await setup_exc_data(assets, "batch-seq")
    executor_task = asyncio.ensure_future(start_executor(data))
    await jobs_mock.mark_done("task-1")
    descr = await jobs_mock.get_task("task-2")
    assert descr.status == JobStatus.PENDING

    await cancel_batch(assets, _executor_data_to_bake_id(data))
    await executor_task

    descr = await jobs_mock.get_task("task-1")
    assert descr.status == JobStatus.SUCCEEDED

    descr = await jobs_mock.get_task("task-2")
    assert descr.status == JobStatus.CANCELLED


async def test_volumes_parsing(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-volumes-parsing"))

    descr = await jobs_mock.get_task("task-1")

    storage_volume = descr.container.volumes[0]
    assert "folder" in storage_volume.storage_uri.path
    assert storage_volume.container_path == "/mnt/storage"
    assert not storage_volume.read_only

    disk_volume = descr.container.disk_volumes[0]
    assert "disk-name" in disk_volume.disk_uri.path
    assert disk_volume.container_path == "/mnt/disk"
    assert disk_volume.read_only

    secret_file = descr.container.secret_files[0]
    assert "key" in secret_file.secret_uri.path
    assert secret_file.container_path == "/mnt/secret"

    await jobs_mock.mark_done("task-1")
    await executor_task


async def test_graphs(
    assets: Path,
    batch_storage: BatchStorage,
    setup_exc_data: Callable[[Path, str], Awaitable[ExecutorData]],
) -> None:
    data = await setup_exc_data(assets, "batch-action-call")
    bake = await batch_storage.fetch_bake(
        data.project, data.batch, data.when, data.suffix
    )
    assert bake.graphs == {
        (): {("test",): set()},
        ("test",): {
            ("test", "task_1"): set(),
            ("test", "task_2"): {("test", "task_1")},
        },
    }


async def test_always_after_disabled(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets, "batch-disabled-but-always")
    )

    await jobs_mock.mark_done("task-2")

    await executor_task


async def test_always_during_cancellation(
    jobs_mock: JobsMock,
    assets: Path,
    setup_exc_data: Callable[[Path, str], Awaitable[ExecutorData]],
    start_executor: Callable[[ExecutorData], Awaitable[None]],
    cancel_batch: Callable[[Path, str], Awaitable[ExecutorData]],
) -> None:
    data = await setup_exc_data(assets, "batch-last-always")
    executor_task = asyncio.ensure_future(start_executor(data))
    descr = await jobs_mock.get_task("task-1")
    assert descr.status == JobStatus.PENDING

    await cancel_batch(assets, _executor_data_to_bake_id(data))

    await jobs_mock.mark_done("task-3")

    await executor_task


async def test_local_action(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    with TemporaryDirectory() as dir:
        ws = LocalPath(dir) / "local_actions"
        shutil.copytree(assets / "local_actions", ws)

        executor_task = asyncio.ensure_future(run_executor(ws, "call-cp"))
        descr = await jobs_mock.get_task("remote-task")
        assert descr.container.command
        assert "echo 0" in descr.container.command

        assert (ws / "file").read_text() == "test\n"
        assert (ws / "file_copy").read_text() == "test\n"

        await jobs_mock.mark_done("remote-task")

        await executor_task


async def test_stateful_no_post(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets / "stateful_actions", "call-no-post")
    )

    await jobs_mock.mark_done("first")
    await jobs_mock.mark_done("test")
    await jobs_mock.mark_done("last")

    await executor_task


async def test_stateful_with_post(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets / "stateful_actions", "call-with-post")
    )

    await jobs_mock.mark_done("first")
    await jobs_mock.mark_done("test")
    await jobs_mock.mark_done("last")
    await jobs_mock.mark_done("post-test")

    await executor_task


async def test_stateful_with_state(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets / "stateful_actions", "call-with-state")
    )

    await jobs_mock.mark_done("first")
    await jobs_mock.mark_done("test", "::save-state name=const::constant".encode())
    await jobs_mock.mark_done("last")
    await jobs_mock.mark_done("post-test")

    await executor_task


async def test_stateful_post_after_fail(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets / "stateful_actions", "call-with-post")
    )

    await jobs_mock.mark_done("first")
    await jobs_mock.mark_done("test")
    await jobs_mock.mark_failed("last")
    await jobs_mock.mark_done("post-test")

    await executor_task


async def test_stateful_post_after_cancellation(
    jobs_mock: JobsMock,
    assets: Path,
    setup_exc_data: Callable[[Path, str], Awaitable[ExecutorData]],
    start_executor: Callable[[ExecutorData], Awaitable[None]],
    cancel_batch: Callable[[Path, str], Awaitable[ExecutorData]],
) -> None:
    data = await setup_exc_data(assets / "stateful_actions", "call-with-post")
    executor_task = asyncio.ensure_future(start_executor(data))
    await jobs_mock.mark_done("first")
    await jobs_mock.mark_done("test")

    await cancel_batch(assets / "stateful_actions", _executor_data_to_bake_id(data))

    await jobs_mock.mark_done("post-test")

    await executor_task
