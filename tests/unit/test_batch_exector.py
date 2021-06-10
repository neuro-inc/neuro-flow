from dataclasses import replace

import asyncio
import pytest
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta
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
    Tag,
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
    Type,
    Union,
)
from yarl import URL

from neuro_flow.batch_executor import BatchExecutor, ExecutorData, LocalsBatchExecutor
from neuro_flow.batch_runner import BatchRunner
from neuro_flow.parser import ConfigDir
from neuro_flow.storage import (
    Bake,
    BakeImage,
    FileSystem,
    FinishedTask,
    FSStorage,
    LocalFS,
    Storage,
    _Unset,
)
from neuro_flow.types import FullID, ImageStatus, LocalPath, TaskStatus


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

    async def _get_task(self, job_id_or_task_name: str) -> JobDescription:
        job_id = job_id_or_task_name
        task_name = job_id_or_task_name.replace("_", "-")
        while True:
            if job_id in self._data:
                return self._data[job_id]
            for descr in self._data.values():
                if f"task:{task_name}" in descr.tags:
                    return descr
            await asyncio.sleep(0.01)

    async def get_task(
        self, job_id_or_task_name: str, timeout: float = 2
    ) -> JobDescription:
        try:
            return await asyncio.wait_for(
                self._get_task(job_id_or_task_name), timeout=timeout
            )
        except asyncio.TimeoutError:
            raise AssertionError(
                f'Task "{job_id_or_task_name}" did not appeared in timeout of {timeout}'
            )

    async def mark_started(self, job_id_or_task_name: str) -> None:
        descr = await self.get_task(job_id_or_task_name)
        if descr.status == JobStatus.PENDING:
            descr = replace(descr, status=JobStatus.RUNNING)
            new_history = replace(
                descr.history, status=JobStatus.RUNNING, started_at=datetime.now()
            )
            descr = replace(descr, history=new_history)
            self._data[descr.id] = descr

    async def mark_done(self, job_id_or_task_name: str, output: bytes = b"") -> None:
        await self.mark_started(job_id_or_task_name)
        descr = await self.get_task(job_id_or_task_name)
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

    async def mark_failed(self, job_id_or_task_name: str, output: bytes = b"") -> None:
        await self.mark_started(job_id_or_task_name)
        descr = await self.get_task(job_id_or_task_name)
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


class ImagesMock:
    def __init__(self) -> None:
        self.known_images: Dict[str, Tag] = {}

    async def tag_info(self, remote: RemoteImage) -> Tag:
        tag = self.known_images.get(str(remote))
        if tag:
            return tag
        raise ResourceNotFound

    async def _close(self) -> None:
        pass


class MockStorage(FSStorage):
    def __init__(self, fs: FileSystem) -> None:
        super().__init__(fs)
        self._bake_images: Dict[str, List[BakeImage]] = defaultdict(list)
        self._index = 0

    async def create_bake_image(
        self,
        bake: Bake,
        yaml_defs: Sequence[FullID],
        ref: str,
        context_on_storage: Optional[URL],
        dockerfile_rel: Optional[str],
    ) -> BakeImage:
        image = BakeImage(
            id=f"image-{self._index}",
            ref=ref,
            yaml_defs=yaml_defs,
            context_on_storage=context_on_storage,
            dockerfile_rel=dockerfile_rel,
            status=ImageStatus.PENDING,
            builder_job_id=None,
        )
        self._index += 1
        self._bake_images[bake.bake_id].append(image)
        return image

    async def list_bake_images(self, bake: Bake) -> AsyncIterator[BakeImage]:
        for image in self._bake_images[bake.bake_id]:
            yield image

    async def get_bake_image(self, bake: Bake, ref: str) -> BakeImage:
        for image in self._bake_images[bake.bake_id]:
            if image.ref == ref:
                return image
        raise ResourceNotFound

    async def update_bake_image(
        self,
        bake: Bake,
        ref: str,
        status: Union[ImageStatus, Type[_Unset]] = _Unset,
        builder_job_id: Union[Optional[str], Type[_Unset]] = _Unset,
    ) -> BakeImage:
        try:
            index, image = next(
                (index, image)
                for index, image in enumerate(self._bake_images[bake.bake_id])
                if image.ref == ref
            )
        except StopIteration:
            raise ResourceNotFound
        if status != _Unset:
            image = replace(image, status=status)
        if builder_job_id != _Unset:
            image = replace(image, builder_job_id=builder_job_id)
        self._bake_images[bake.bake_id][index] = image
        return image


@pytest.fixture()
def batch_storage(loop: None) -> Iterator[Storage]:
    with TemporaryDirectory() as tmpdir:
        fs = LocalFS(Path(tmpdir))
        yield MockStorage(fs)


class FakeGlobalOptions:
    verbosity = 0
    show_traceback = False


class MockCliRunner:
    def __init__(self) -> None:
        self.runs: List[Tuple[str, ...]] = []

    async def run(self, *args: str) -> None:
        self.runs.append(args)


@pytest.fixture()
async def mock_neuro_cli_runner() -> MockCliRunner:
    return MockCliRunner()


class MockBuilder:
    def __init__(self, jobs_mock: JobsMock) -> None:
        self.runs: List[Tuple[str, ...]] = []
        self.jobs = jobs_mock
        self.ref2job: Dict[str, str] = {}

    async def run(self, *args: str) -> str:
        self.runs.append(args)
        job = await self.jobs.start(image=RemoteImage("test"), preset_name="fake")
        self.ref2job[args[-1]] = job.id
        return job.id


@pytest.fixture()
async def mock_builder(
    jobs_mock: JobsMock,
) -> MockBuilder:
    return MockBuilder(jobs_mock)


@pytest.fixture()
async def make_batch_runner(
    batch_storage: Storage,
    client: Client,
    mock_neuro_cli_runner: MockCliRunner,
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
            client,
            batch_storage,
            FakeGlobalOptions(),
            run_neuro_cli=mock_neuro_cli_runner.run,
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
def images_mock() -> ImagesMock:
    return ImagesMock()


@pytest.fixture()
async def patched_client(
    api_config: Path, jobs_mock: JobsMock, images_mock: ImagesMock
) -> AsyncIterator[Client]:
    async with api_get(path=api_config) as client:
        client._jobs = jobs_mock
        client._images = images_mock  # type: ignore
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
    batch_storage: Storage,
    patched_client: Client,
    mock_builder: MockBuilder,
) -> Callable[[ExecutorData], Awaitable[None]]:
    async def start(data: ExecutorData) -> None:
        async with BatchExecutor.create(
            get_console(),
            data,
            patched_client,
            batch_storage,
            polling_timeout=0.05,
            run_builder_job=mock_builder.run,
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


async def test_batch_with_module_ok(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets / "batch_module", "batch-module-call")
    )
    task = await jobs_mock.get_task("test.task-1")
    assert task.container.command
    assert "batch_module_call" in task.container.command
    assert task.container.env.get("TEST") == "test_value"
    assert "test-tag" in task.tags
    assert task.preset_name == "test-preset"
    assert task.life_span == timedelta(days=2).total_seconds()
    assert task.schedule_timeout == timedelta(minutes=60).total_seconds()
    assert task.container.working_dir == "/some/dir"
    assert task.container.volumes[0].container_path == "/volume"
    await jobs_mock.mark_done("test.task-1", b"::set-output name=task1::Task 1 val 1")

    task = await jobs_mock.get_task("test.task-2")
    assert task.container.command
    assert "batch_module_call" in task.container.command
    assert task.container.env.get("TEST") == "test_value"
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


async def _wait_for_build(mock_builder: MockBuilder, ref: str) -> str:
    async def _waiter() -> None:
        while ref not in mock_builder.ref2job:
            await asyncio.sleep(0.1)

    await asyncio.wait_for(_waiter(), timeout=1)
    return mock_builder.ref2job[ref]


async def test_image_builds(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
    mock_builder: MockBuilder,
    batch_storage: Storage,
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets / "batch_images", "batch")
    )

    job_id = await _wait_for_build(mock_builder, "image:banana1")
    bake = [bake async for bake in batch_storage.list_bakes("batch_images")][0]
    image = await batch_storage.get_bake_image(bake, "image:banana1")
    assert mock_builder.runs[-1] == (
        "neuro-extras",
        "image",
        "build",
        "--file=Dockerfile",
        str(image.context_on_storage),
        "image:banana1",
    )
    await jobs_mock.mark_done(job_id)

    task = await jobs_mock.get_task("action.task_1")
    assert task.container.image.name == "banana1"
    await jobs_mock.mark_done("action.task_1")

    job_id = await _wait_for_build(mock_builder, "image:banana2")
    assert mock_builder.runs[-1] == (
        "neuro-extras",
        "image",
        "build",
        "--file=Dockerfile",
        "storage://default/foo/val1",
        "image:banana2",
    )
    await jobs_mock.mark_done(job_id)

    task = await jobs_mock.get_task("action.task_2")
    assert task.container.image.name == "banana2"
    await jobs_mock.mark_done("action.task_2")

    job_id = await _wait_for_build(mock_builder, "image:main")
    image = await batch_storage.get_bake_image(bake, "image:main")
    assert mock_builder.runs[-1] == (
        "neuro-extras",
        "image",
        "build",
        "--file=Dockerfile",
        str(image.context_on_storage),
        "image:main",
    )
    await jobs_mock.mark_done(job_id)

    task = await jobs_mock.get_task("task")
    assert task.container.image.name == "main"
    await jobs_mock.mark_done("task")

    await asyncio.wait_for(executor_task, timeout=1)


async def test_image_builds_skip_if_present(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
    images_mock: ImagesMock,
    client: Client,
) -> None:
    images_mock.known_images = {
        f"image://{client.cluster_name}/{client.username}/banana1:latest": Tag(
            "latest"
        ),
        f"image://{client.cluster_name}/{client.username}/banana2:latest": Tag(
            "latest"
        ),
        f"image://{client.cluster_name}/{client.username}/main:latest": Tag("latest"),
    }

    executor_task = asyncio.ensure_future(
        run_executor(assets / "batch_images", "batch")
    )

    await jobs_mock.get_task("action.task_1")
    await jobs_mock.mark_done("action.task_1")

    await jobs_mock.get_task("action.task_2")
    await jobs_mock.mark_done("action.task_2")

    await jobs_mock.get_task("task")
    await jobs_mock.mark_done("task")

    await asyncio.wait_for(executor_task, timeout=1)


async def test_image_builds_if_present_but_force(
    jobs_mock: JobsMock,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
    images_mock: ImagesMock,
    mock_builder: MockBuilder,
    batch_storage: Storage,
    client: Client,
) -> None:
    images_mock.known_images = {
        f"image://{client.cluster_name}/{client.username}/banana1:latest": Tag(
            "latest"
        ),
        f"image://{client.cluster_name}/{client.username}/banana2:latest": Tag(
            "latest"
        ),
        f"image://{client.cluster_name}/{client.username}/main:latest": Tag("latest"),
    }

    executor_task = asyncio.ensure_future(
        run_executor(assets / "batch_images", "batch-with-force")
    )

    await jobs_mock.get_task("action.task_1")
    await jobs_mock.mark_done("action.task_1")

    await jobs_mock.get_task("action.task_2")
    await jobs_mock.mark_done("action.task_2")

    job_id = await _wait_for_build(mock_builder, "image:main")
    bake = [bake async for bake in batch_storage.list_bakes("batch_images")][0]
    image = await batch_storage.get_bake_image(bake, "image:main")
    assert mock_builder.runs[-1] == (
        "neuro-extras",
        "image",
        "build",
        "--file=Dockerfile",
        "--force-overwrite",
        str(image.context_on_storage),
        "image:main",
    )
    await jobs_mock.mark_done(job_id)

    await jobs_mock.get_task("task")
    await jobs_mock.mark_done("task")

    await asyncio.wait_for(executor_task, timeout=1)


async def test_image_builds_cancel(
    jobs_mock: JobsMock,
    make_batch_runner: MakeBatchRunner,
    assets: Path,
    run_executor: Callable[[Path, str], Awaitable[None]],
    mock_builder: MockBuilder,
    batch_storage: Storage,
) -> None:
    executor_task = asyncio.ensure_future(
        run_executor(assets / "batch_images", "batch")
    )
    batch_runner = await make_batch_runner(assets / "batch_images")

    async def _wait_for_build(ref: str) -> str:
        async def _waiter() -> None:
            while ref not in mock_builder.ref2job:
                await asyncio.sleep(0.1)

        await asyncio.wait_for(_waiter(), timeout=1)
        return mock_builder.ref2job[ref]

    job_id = await _wait_for_build("image:banana1")
    bake = [bake async for bake in batch_storage.list_bakes("batch_images")][0]
    await batch_runner.cancel(bake.bake_id)

    await asyncio.wait_for(executor_task, timeout=1)

    descr = await jobs_mock.get_task(job_id)
    assert descr.status == JobStatus.CANCELLED
