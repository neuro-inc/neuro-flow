from dataclasses import replace

import asyncio
import pytest
import shutil
import sys
from datetime import datetime
from neuro_sdk import (
    Client,
    Container,
    DiskVolume,
    HTTPPort,
    JobDescription,
    JobRestartPolicy,
    JobStatus,
    JobStatusHistory,
    RemoteImage,
    ResourceNotFound,
    Resources,
    SecretFile,
    Volume,
    get as api_get,
)
from pathlib import Path
from rich import get_console
from tempfile import TemporaryDirectory
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    cast,
)
from yarl import URL

from neuro_flow.batch_executor import BatchExecutor, ExecutorData, LocalsBatchExecutor
from neuro_flow.batch_runner import BatchRunner
from neuro_flow.parser import ConfigDir
from neuro_flow.storage import Bake, FinishedTask, FSStorage, LocalFS, Storage
from neuro_flow.types import LocalPath, TaskStatus


MakeBatchRunner = Callable[[Path], Awaitable[BatchRunner]]


def make_descr(
    job_id: str,
    *,
    status: JobStatus = JobStatus.PENDING,
    tags: Iterable[str] = (),
    description: str = "",
    scheduler_enabled: bool = False,
    created_at: datetime = datetime.now(),
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    exit_code: Optional[int] = None,
    restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER,
    life_span: float = 3600,
    name: Optional[str] = None,
    container: Optional[Container] = None,
    pass_config: bool = False,
) -> JobDescription:
    if container is None:
        container = Container(RemoteImage("ubuntu"), Resources(100, 0.1))

    return JobDescription(
        id=job_id,
        owner="test-user",
        cluster_name="default",
        status=status,
        history=JobStatusHistory(
            status=status,
            reason="",
            description="",
            restarts=0,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
        ),
        container=container,
        scheduler_enabled=scheduler_enabled,
        uri=URL(f"job://default/test-user/{job_id}"),
        name=name,
        tags=sorted(
            list(set(tags) | {"project:test", "flow:batch-seq", f"task:{job_id}"})
        ),
        description=description,
        restart_policy=restart_policy,
        life_span=life_span,
        pass_config=pass_config,
    )


class JobsMock:
    # Mock for client.jobs subsystem

    _data: Dict[str, JobDescription]
    _outputs: Dict[str, bytes]
    exception_on_status: Optional[BaseException]

    def __init__(self) -> None:
        self.id_counter = 0
        self._data = {}
        self._outputs = {}
        self.exception_on_status = None

    def _make_next_id(self) -> int:
        self.id_counter += 1
        return self.id_counter

    # Method for controlling in tests

    async def _get_task(self, task_name: str) -> JobDescription:
        while True:
            for descr in self._data.values():
                task_name = task_name.replace("_", "-")
                if f"task:{task_name}" in descr.tags:
                    return descr
            await asyncio.sleep(0.01)

    async def get_task(self, task_name: str, timeout: float = 2) -> JobDescription:
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

    def clear(self) -> None:
        self._data = {}
        self._outputs = {}

    # Fake Jobs methods

    async def start(
        self,
        *,
        image: RemoteImage,
        preset_name: str,
        entrypoint: Optional[str] = None,
        command: Optional[str] = None,
        working_dir: Optional[str] = None,
        http: Optional[HTTPPort] = None,
        env: Optional[Mapping[str, str]] = None,
        volumes: Sequence[Volume] = (),
        secret_env: Optional[Mapping[str, URL]] = None,
        secret_files: Sequence[SecretFile] = (),
        disk_volumes: Sequence[DiskVolume] = (),
        tty: bool = False,
        shm: bool = False,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
        description: Optional[str] = None,
        pass_config: bool = False,
        wait_for_jobs_quota: bool = False,
        schedule_timeout: Optional[float] = None,
        restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER,
        life_span: Optional[float] = None,
        privileged: bool = False,
    ) -> JobDescription:
        job_id = f"job-{self._make_next_id()}"

        resources = Resources(cpu=1, memory_mb=1, shm=shm)
        container = Container(
            image=image,
            entrypoint=entrypoint,
            command=command,
            http=http,
            resources=resources,
            env=env or {},
            secret_env=secret_env or {},
            volumes=volumes,
            working_dir=working_dir,
            secret_files=secret_files,
            disk_volumes=disk_volumes,
            tty=tty,
        )
        self._data[job_id] = JobDescription(
            id=job_id,
            owner="test-user",
            cluster_name="default",
            preset_name=preset_name,
            status=JobStatus.PENDING,
            history=JobStatusHistory(
                status=JobStatus.PENDING,
                reason="",
                description="",
                created_at=datetime.now(),
                restarts=0,
            ),
            container=container,
            scheduler_enabled=False,
            uri=URL(f"job://default/test-user/{job_id}"),
            name=name,
            tags=tags,
            description=description,
            restart_policy=restart_policy,
            life_span=life_span,
            pass_config=pass_config,
            privileged=privileged,
            schedule_timeout=schedule_timeout,
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
        if self.exception_on_status:
            raise self.exception_on_status
        try:
            return self._data[job_id]
        except KeyError:
            raise ResourceNotFound

    async def monitor(self, job_id: str) -> AsyncIterator[bytes]:
        yield self._outputs.get(job_id, b"")


@pytest.fixture()
def batch_storage(loop: None) -> Iterator[Storage]:
    with TemporaryDirectory() as tmpdir:
        fs = LocalFS(Path(tmpdir))
        yield FSStorage(fs)


class FakeGlobalOptions:
    verbosity = 0
    show_traceback = False


@pytest.fixture()
async def make_batch_runner(
    batch_storage: Storage,
) -> AsyncIterator[MakeBatchRunner]:

    runner: Optional[BatchRunner] = None

    async def create(path: Path) -> BatchRunner:
        config_dir = ConfigDir(
            workspace=path,
            config_dir=path,
        )
        nonlocal runner
        # BatchRunner should not use client in this case

        runner = BatchRunner(
            config_dir,
            get_console(),
            cast(Client, None),
            batch_storage,
            FakeGlobalOptions(),
        )
        await runner.__aenter__()
        return runner

    yield create

    if runner is not None:
        await runner.__aexit__(None, None, None)


@pytest.fixture()
async def batch_runner(
    make_batch_runner: MakeBatchRunner,
    assets: Path,
) -> BatchRunner:
    return await make_batch_runner(assets)


@pytest.fixture()
def jobs_mock() -> JobsMock:
    return JobsMock()


@pytest.fixture()
async def patched_client(
    api_config: Path, jobs_mock: JobsMock
) -> AsyncIterator[Client]:
    async with api_get(path=api_config) as client:
        client._jobs = jobs_mock
        yield client


@pytest.fixture()
def start_locals_executor(
    batch_storage: Storage, patched_client: Client
) -> Callable[[ExecutorData], Awaitable[TaskStatus]]:
    async def start(data: ExecutorData) -> TaskStatus:
        async with LocalsBatchExecutor.create(
            get_console(),
            data,
            patched_client,
            batch_storage,
        ) as executor:
            return await executor.run()

    return start


@pytest.fixture()
def start_executor(
    batch_storage: Storage, patched_client: Client
) -> Callable[[ExecutorData], Awaitable[None]]:
    async def start(data: ExecutorData) -> None:
        async with BatchExecutor.create(
            get_console(),
            data,
            patched_client,
            batch_storage,
            polling_timeout=0.05,
        ) as executor:
            await executor.run()

    return start


RunExecutor = Callable[
    [Path, str], Awaitable[Tuple[Dict[Tuple[str, ...], FinishedTask], TaskStatus]]
]


@pytest.fixture()
def run_executor(
    make_batch_runner: MakeBatchRunner,
    start_locals_executor: Callable[[ExecutorData], Awaitable[None]],
    start_executor: Callable[[ExecutorData], Awaitable[None]],
    batch_storage: Storage,
) -> RunExecutor:
    async def run(
        config_loc: Path, batch_name: str, args: Optional[Mapping[str, str]] = None
    ) -> Tuple[Dict[Tuple[str, ...], FinishedTask], TaskStatus]:
        runner = await make_batch_runner(config_loc)
        data, _ = await runner._setup_bake(batch_name, args)
        status = await start_locals_executor(data)
        if status == TaskStatus.SUCCEEDED:
            await start_executor(data)
        bake = await batch_storage.fetch_bake(
            data.project, data.batch, data.when, data.suffix
        )
        attempt = await batch_storage.find_attempt(bake)
        _, finished = await batch_storage.fetch_attempt(attempt)
        return finished, attempt.result

    return run


def _executor_data_to_bake_id(data: ExecutorData) -> str:
    return Bake(
        project=data.project,
        batch=data.batch,
        when=data.when,
        suffix=data.suffix,
        graphs={},  # not needed for bake_id calculation
        params={},
        name=None,
        tags=(),
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


async def test_complex_seq(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-complex-seq"))
    await jobs_mock.get_task("task_1_a")
    await jobs_mock.get_task("task_1_b")

    await jobs_mock.mark_started("task_1_a")
    await jobs_mock.mark_started("task_1_b")

    await jobs_mock.get_task("task_2_at_running.task_1")
    await jobs_mock.mark_done(
        "task_2_at_running.task_1", b"::set-output name=task1::Task 1 val 1"
    )
    await jobs_mock.get_task("task_2_at_running.task_2")

    await jobs_mock.mark_done("task_1_a")
    await jobs_mock.mark_done("task_1_b")

    await jobs_mock.get_task("task_2_after")
    await jobs_mock.mark_done("task_2_after")

    with pytest.raises(AssertionError, match=r".* did not appeared in timeout of .*"):
        await jobs_mock.get_task("task_3", timeout=0.5)

    await jobs_mock.mark_started("task_2_at_running.task_2")

    await jobs_mock.get_task("task_3")
    await jobs_mock.mark_done("task_3")

    await jobs_mock.mark_done(
        "task_2_at_running.task_2", b"::set-output name=task2::Task 2 val 2"
    )

    await asyncio.wait_for(executor_task, timeout=5)


class FakeForceStopException(BaseException):
    # Used to simulate almost instant kills of executor
    pass


def run_in_loop(coro: Awaitable[Any]) -> Any:
    loop = asyncio.new_event_loop()
    return loop.run_until_complete(coro)


async def test_complex_seq_continue(
    jobs_mock: JobsMock,
    batch_storage: Storage,
    start_executor: Callable[[ExecutorData], Awaitable[None]],
    batch_runner: BatchRunner,
) -> None:
    data, _ = await batch_runner._setup_bake("batch-complex-seq")
    # Use separate thread to allow force abort
    executor_task = asyncio.get_event_loop().run_in_executor(
        None, run_in_loop, start_executor(data)
    )

    await jobs_mock.get_task("task_1_a")
    await jobs_mock.get_task("task_1_b")

    await jobs_mock.mark_started("task_1_a")
    await jobs_mock.mark_started("task_1_b")

    await jobs_mock.get_task("task_2_at_running.task_1")
    await jobs_mock.mark_done(
        "task_2_at_running.task_1", b"::set-output name=task1::Task 1 val 1"
    )
    await jobs_mock.get_task("task_2_at_running.task_2")

    await jobs_mock.mark_done("task_1_a")
    await jobs_mock.mark_done("task_1_b")

    await jobs_mock.get_task("task_2_after")
    await jobs_mock.mark_done("task_2_after")

    jobs_mock.exception_on_status = FakeForceStopException()
    try:
        await executor_task
    except FakeForceStopException:
        pass
    jobs_mock.exception_on_status = None

    executor_task_2 = asyncio.ensure_future(start_executor(data))

    await jobs_mock.mark_started("task_2_at_running.task_2")

    await jobs_mock.get_task("task_3")
    await jobs_mock.mark_done("task_3")

    await jobs_mock.mark_done(
        "task_2_at_running.task_2", b"::set-output name=task2::Task 2 val 2"
    )

    await asyncio.wait_for(executor_task_2, timeout=5)


async def test_complex_seq_continue_2(
    jobs_mock: JobsMock,
    batch_storage: Storage,
    start_executor: Callable[[ExecutorData], Awaitable[None]],
    batch_runner: BatchRunner,
) -> None:
    data, _ = await batch_runner._setup_bake("batch-complex-seq")
    # Use separate thread to allow force abort
    executor_task = asyncio.get_event_loop().run_in_executor(
        None, run_in_loop, start_executor(data)
    )

    await jobs_mock.get_task("task_1_a")
    await jobs_mock.get_task("task_1_b")

    await jobs_mock.mark_started("task_1_a")
    await jobs_mock.mark_started("task_1_b")

    await jobs_mock.get_task("task_2_at_running.task_1")
    await jobs_mock.mark_done(
        "task_2_at_running.task_1", b"::set-output name=task1::Task 1 val 1"
    )
    await jobs_mock.get_task("task_2_at_running.task_2")
    await jobs_mock.mark_started("task_2_at_running.task_2")

    jobs_mock.exception_on_status = FakeForceStopException()
    try:
        await executor_task
    except FakeForceStopException:
        pass
    jobs_mock.exception_on_status = None

    await jobs_mock.mark_done(
        "task_2_at_running.task_2", b"::set-output name=task2::Task 2 val 2"
    )

    executor_task_2 = asyncio.ensure_future(start_executor(data))

    await jobs_mock.mark_done("task_1_a")
    await jobs_mock.mark_done("task_1_b")

    await jobs_mock.get_task("task_2_after")
    await jobs_mock.mark_done("task_2_after")

    await jobs_mock.get_task("task_3")
    await jobs_mock.mark_done("task_3")

    await asyncio.wait_for(executor_task_2, timeout=5)


async def test_complex_seq_restart(
    jobs_mock: JobsMock,
    batch_storage: Storage,
    start_executor: Callable[[ExecutorData], Awaitable[None]],
    batch_runner: BatchRunner,
) -> None:
    data, _ = await batch_runner._setup_bake("batch-complex-seq")
    executor_task = asyncio.ensure_future(start_executor(data))

    await jobs_mock.get_task("task_1_a")
    await jobs_mock.get_task("task_1_b")

    await jobs_mock.mark_started("task_1_a")
    await jobs_mock.mark_started("task_1_b")

    await jobs_mock.get_task("task_2_at_running.task_1")
    await jobs_mock.mark_done(
        "task_2_at_running.task_1", b"::set-output name=task1::Task 1 val 1"
    )
    await jobs_mock.get_task("task_2_at_running.task_2")

    await jobs_mock.mark_done("task_1_a")
    await jobs_mock.mark_done("task_1_b")

    await jobs_mock.get_task("task_2_after")
    await jobs_mock.mark_done("task_2_after")

    await asyncio.sleep(0.1)  # Let loop proceed

    await jobs_mock.mark_failed("task_2_at_running.task_2")

    await asyncio.wait_for(executor_task, timeout=5)

    jobs_mock.clear()
    data, _ = await batch_runner._restart(_executor_data_to_bake_id(data))

    executor_task = asyncio.ensure_future(start_executor(data))

    await jobs_mock.get_task("task_2_at_running.task_2")
    await jobs_mock.mark_started("task_2_at_running.task_2")

    await jobs_mock.get_task("task_3")
    await jobs_mock.mark_done("task_3")

    await jobs_mock.mark_done(
        "task_2_at_running.task_2", b"::set-output name=task2::Task 2 val 2"
    )

    await asyncio.wait_for(executor_task, timeout=5)


async def test_workdir_passed(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-workdir"))
    task_descr = await jobs_mock.get_task("task-1")
    assert task_descr.container.working_dir == "/test/workdir"
    await jobs_mock.mark_done("task-1")

    await executor_task


async def test_batch_with_action_ok(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-action-call"))
    await jobs_mock.get_task("test.task-1")
    await jobs_mock.mark_done("test.task-1", b"::set-output name=task1::Task 1 val 1")

    await jobs_mock.get_task("test.task-2")
    await jobs_mock.mark_done("test.task-2", b"::set-output name=task2::Task 2 value 2")
    await executor_task


@pytest.mark.parametrize(
    "batch_name,vars",
    [
        ("batch-matrix-1", [("o1", "t1"), ("o1", "t2"), ("o2", "t1"), ("o2", "t2")]),
        ("batch-matrix-2", [("o1", "t2"), ("o2", "t1"), ("o2", "t2")]),
        (
            "batch-matrix-3",
            [("o1", "t1"), ("o1", "t2"), ("o2", "t1"), ("o2", "t2"), ("o3", "t3")],
        ),
        ("batch-matrix-4", [("o2", "t1"), ("o2", "t2"), ("o3", "t3")]),
        ("batch-matrix-5", [("o2", "t1"), ("o2", "t2"), ("o1", "t1")]),
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


@pytest.mark.parametrize(
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
    await asyncio.wait_for(run_executor(assets, "batch-first-disabled"), timeout=5)


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
    batch_runner: BatchRunner,
    start_executor: Callable[[ExecutorData], Awaitable[None]],
) -> None:
    data, _ = await batch_runner._setup_bake("batch-seq")
    executor_task = asyncio.ensure_future(start_executor(data))
    await jobs_mock.mark_done("task-1")
    descr = await jobs_mock.get_task("task-2")
    assert descr.status == JobStatus.PENDING

    await batch_runner.cancel(_executor_data_to_bake_id(data))
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
    batch_storage: Storage,
    batch_runner: BatchRunner,
) -> None:
    data, _ = await batch_runner._setup_bake("batch-action-call")
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


async def test_early_graph(
    batch_storage: Storage,
    make_batch_runner: MakeBatchRunner,
    assets: Path,
) -> None:
    batch_runner = await make_batch_runner(assets / "early_graph")
    data, _ = await batch_runner._setup_bake("batch")
    bake = await batch_storage.fetch_bake(
        data.project, data.batch, data.when, data.suffix
    )
    assert bake.graphs == {
        (): {
            ("first_ac",): set(),
            ("second",): {("first_ac",)},
            ("third",): {("first_ac",)},
        },
        ("first_ac",): {("first_ac", "task_2"): set()},
        ("second",): {
            ("second", "task-1-o3-t3"): set(),
            ("second", "task-1-o1-t1"): set(),
            ("second", "task-1-o2-t1"): set(),
            ("second", "task-1-o2-t2"): set(),
            ("second", "task_2"): {
                ("second", "task-1-o3-t3"),
                ("second", "task-1-o1-t1"),
                ("second", "task-1-o2-t1"),
                ("second", "task-1-o2-t2"),
            },
        },
        ("third",): {
            ("third", "task-1-o3-t3"): set(),
            ("third", "task-1-o1-t1"): set(),
            ("third", "task-1-o2-t1"): set(),
            ("third", "task-1-o2-t2"): set(),
            ("third", "task_2"): {
                ("third", "task-1-o3-t3"),
                ("third", "task-1-o1-t1"),
                ("third", "task-1-o2-t1"),
                ("third", "task-1-o2-t2"),
            },
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
    batch_runner: BatchRunner,
    start_executor: Callable[[ExecutorData], Awaitable[None]],
) -> None:
    data, _ = await batch_runner._setup_bake("batch-last-always")
    executor_task = asyncio.ensure_future(start_executor(data))
    descr = await jobs_mock.get_task("task-1")
    assert descr.status == JobStatus.PENDING

    await batch_runner.cancel(_executor_data_to_bake_id(data))

    await jobs_mock.mark_done("task-3")

    await executor_task


@pytest.mark.skipif(
    sys.platform == "win32", reason="cp command is not support by Windows"
)
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


@pytest.mark.skipif(
    sys.platform == "win32", reason="cp command is not support by Windows"
)
async def test_action_with_local_action(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    with TemporaryDirectory() as dir:
        ws = LocalPath(dir) / "local_actions"
        shutil.copytree(assets / "local_actions", ws)

        executor_task = asyncio.ensure_future(
            run_executor(ws, "call-batch-action-with-local")
        )
        descr = await jobs_mock.get_task("call_action.remote-task")
        assert descr.container.command
        assert "echo 0" in descr.container.command

        assert (ws / "file").read_text() == "test\n"
        assert (ws / "file_copy").read_text() == "test\n"

        await jobs_mock.mark_done("call_action.remote-task")

        await executor_task


async def test_local_deps_on_remote_1(
    jobs_mock: JobsMock,
    assets: Path,
    make_batch_runner: MakeBatchRunner,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    batch_runner = await make_batch_runner(assets / "local_actions")
    with pytest.raises(
        Exception, match=r"Local action 'local' depends on remote task 'remote'"
    ):
        await batch_runner._setup_bake("bad-order")


async def test_local_deps_on_remote_2(
    jobs_mock: JobsMock,
    assets: Path,
    make_batch_runner: MakeBatchRunner,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    batch_runner = await make_batch_runner(assets / "local_actions")
    with pytest.raises(
        Exception,
        match=r"Local action 'local' depends on "
        r"remote task 'call_action.remote_task'",
    ):
        await batch_runner._setup_bake("bad-order-through-action")


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
    await jobs_mock.mark_done("test", b"::save-state name=const::constant")
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
    make_batch_runner: MakeBatchRunner,
    start_executor: Callable[[ExecutorData], Awaitable[None]],
) -> None:
    runner = await make_batch_runner(assets / "stateful_actions")
    data, _ = await runner._setup_bake("call-with-post")
    executor_task = asyncio.ensure_future(start_executor(data))
    await jobs_mock.mark_done("first")
    await jobs_mock.mark_done("test")

    await runner.cancel(_executor_data_to_bake_id(data))

    await jobs_mock.mark_done("post-test")

    await executor_task


async def test_restart(batch_storage: Storage, batch_runner: BatchRunner) -> None:
    data, _ = await batch_runner._setup_bake("batch-seq")
    bake = await batch_storage.fetch_bake(
        data.project, data.batch, data.when, data.suffix
    )
    attempt = await batch_storage.find_attempt(bake)
    job_1 = ("task-1",)
    job_2 = ("task-2",)
    st1 = await batch_storage.start_task(attempt, job_1, make_descr("job:task-1"))
    ft1 = await batch_storage.finish_task(
        attempt,
        st1,
        make_descr(
            "job:task-1",
            status=JobStatus.SUCCEEDED,
            exit_code=0,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        ),
        {},
        {},
    )
    st2 = await batch_storage.start_task(attempt, job_2, make_descr("job:task-2"))
    await batch_storage.finish_task(
        attempt,
        st2,
        make_descr(
            "job:task-2",
            status=JobStatus.FAILED,
            exit_code=1,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        ),
        {},
        {},
    )

    await batch_storage.finish_attempt(attempt, TaskStatus.FAILED)

    data2, _ = await batch_runner._restart(bake.bake_id)
    assert data == data2

    attempt2 = await batch_storage.find_attempt(bake)
    assert attempt2.number == 2
    started, finished = await batch_storage.fetch_attempt(attempt2)
    assert list(started.keys()) == [job_1]
    assert list(finished.keys()) == [job_1]
    assert started[job_1] == replace(st1, attempt=attempt2)
    assert finished[job_1] == replace(ft1, attempt=attempt2)


async def test_restart_not_last_attempt(
    batch_storage: Storage, batch_runner: BatchRunner
) -> None:
    data, _ = await batch_runner._setup_bake("batch-seq")
    bake = await batch_storage.fetch_bake(
        data.project, data.batch, data.when, data.suffix
    )
    attempt = await batch_storage.find_attempt(bake)
    job_1 = ("task-1",)
    job_2 = ("task-2",)
    st1 = await batch_storage.start_task(attempt, job_1, make_descr("job:task-1"))
    ft1 = await batch_storage.finish_task(
        attempt,
        st1,
        make_descr(
            "job:task-1",
            status=JobStatus.SUCCEEDED,
            exit_code=0,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        ),
        {},
        {},
    )
    st2 = await batch_storage.start_task(attempt, job_2, make_descr("job:task-2"))
    await batch_storage.finish_task(
        attempt,
        st2,
        make_descr(
            "job:task-2",
            status=JobStatus.FAILED,
            exit_code=1,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        ),
        {},
        {},
    )

    await batch_storage.finish_attempt(attempt, TaskStatus.FAILED)

    await batch_runner._restart(bake.bake_id)

    data3, _ = await batch_runner._restart(bake.bake_id, attempt_no=1)
    assert data == data3

    attempt3 = await batch_storage.find_attempt(bake)
    assert attempt3.number == 3
    started, finished = await batch_storage.fetch_attempt(attempt3)
    assert list(started.keys()) == [job_1]
    assert list(finished.keys()) == [job_1]
    assert started[job_1] == replace(st1, attempt=attempt3)
    assert finished[job_1] == replace(ft1, attempt=attempt3)


async def test_fully_cached_simple(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: RunExecutor,
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-seq"))

    await jobs_mock.mark_done("task-1")
    await jobs_mock.mark_done("task-2")
    await executor_task

    finished, status = await asyncio.wait_for(
        run_executor(assets, "batch-seq"), timeout=10
    )
    assert status == TaskStatus.SUCCEEDED
    for task in finished.values():
        assert task.status == TaskStatus.CACHED


async def test_fully_cached_with_action(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: RunExecutor,
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-action-call"))
    await jobs_mock.mark_done("test.task-1", b"::set-output name=task1::Task 1 val 1")
    await jobs_mock.mark_done("test.task-2", b"::set-output name=task2::Task 2 value 2")
    await executor_task

    finished, status = await asyncio.wait_for(
        run_executor(assets, "batch-action-call"), timeout=10
    )

    assert status == TaskStatus.SUCCEEDED
    assert finished[("test", "task_1")].status == TaskStatus.CACHED
    assert finished[("test", "task_2")].status == TaskStatus.CACHED


async def test_cached_same_needs(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: RunExecutor,
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-test-cache"))

    await jobs_mock.mark_done("task-1", b"::set-output name=arg::val")
    await jobs_mock.mark_done("task-2")
    await executor_task

    jobs_mock.clear()
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-test-cache"))

    await jobs_mock.mark_done("task-1", b"::set-output name=arg::val")

    finished, status = await asyncio.wait_for(executor_task, timeout=10)

    assert status == TaskStatus.SUCCEEDED
    assert finished[("task-1",)].status == TaskStatus.SUCCEEDED
    assert finished[("task-2",)].status == TaskStatus.CACHED


async def test_not_cached_if_different_needs(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-test-cache"))

    await jobs_mock.mark_done("task-1", b"::set-output name=arg::val")
    await jobs_mock.mark_done("task-2")
    await executor_task

    jobs_mock.clear()
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-test-cache"))

    await jobs_mock.mark_done("task-1", b"::set-output name=arg::val2")
    await jobs_mock.mark_done("task-2")
    await executor_task


async def test_batch_params(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str, Mapping[str, str]], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets, "batch-params-required", {"arg2": "test_value"})
    )
    task_descr = await jobs_mock.get_task("task-1")
    assert set(task_descr.tags).issuperset(
        {
            "flow:batch-params-required",
            "test_value",
            "val1",
            "project:unit",
            "task:task-1",
        }
    )
    await jobs_mock.mark_done("task-1")

    await executor_task


async def test_batch_bake_id_tag(
    jobs_mock: JobsMock,
    batch_storage: Storage,
    start_executor: Callable[[ExecutorData], Awaitable[None]],
    batch_runner: BatchRunner,
) -> None:
    data, _ = await batch_runner._setup_bake("batch-seq")
    executor_task = asyncio.ensure_future(start_executor(data))

    task_descr = await jobs_mock.get_task("task-1")
    assert set(task_descr.tags) == {
        "flow:batch-seq",
        f"bake_id:{_executor_data_to_bake_id(data)}",
        "project:unit",
        "task:task-1",
    }
    await jobs_mock.mark_done("task-1")

    await jobs_mock.mark_done("task-2")

    await executor_task


async def test_bake_marked_as_failed_on_eval_error(
    assets: Path,
    run_executor: RunExecutor,
) -> None:
    _, status = await run_executor(assets, "batch-bad-eval")
    assert status == TaskStatus.FAILED


async def test_bake_marked_as_failed_on_eval_error_in_local(
    assets: Path,
    run_executor: RunExecutor,
) -> None:
    _, status = await run_executor(assets / "local_actions", "call-bad-local")
    assert status == TaskStatus.FAILED


async def test_bake_marked_as_failed_on_random_error(
    assets: Path,
    run_executor: RunExecutor,
    jobs_mock: JobsMock,
) -> None:
    jobs_mock.exception_on_status = Exception("Something failed")
    _, status = await run_executor(assets, "batch-seq")
    assert status == TaskStatus.FAILED


async def test_bake_marked_as_cancelled_on_task_cancelation(
    assets: Path,
    run_executor: RunExecutor,
) -> None:
    executor_task = asyncio.ensure_future(run_executor(assets, "batch-seq"))
    await asyncio.sleep(0)  # All to start
    executor_task.cancel()
    _, status = await executor_task
    assert status == TaskStatus.CANCELLED
