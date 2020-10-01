import dataclasses

import abc
import collections
import datetime
import enum
import hashlib
import json
import logging
import re
import secrets
import shutil
import sys
from abc import abstractmethod
from neuromation.api import (
    Action,
    Client,
    FileStatus,
    FileStatusType,
    JobDescription,
    JobStatus,
    ResourceNotFound,
)
from types import TracebackType
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    cast,
)
from typing_extensions import Final
from yarl import URL

from neuro_flow.types import LocalPath

from . import ast
from .context import ActionContext, BaseContext, DepCtx, TaskContext
from .types import FullID, RemotePath, TaskStatus


if sys.version_info < (3, 7):
    from backports.datetime_fromisoformat import MonkeyPatch

    MonkeyPatch.patch_fromisoformat()


log = logging.getLogger(__name__)

STARTED_RE: Final = re.compile(
    r"\A\d+\.(?P<id>[a-zA-Z][a-zA-Z0-9_\-\.]*).started.json\Z"
)
FINISHED_RE: Final = re.compile(
    r"\A\d+\.(?P<id>[a-zA-Z][a-zA-Z0-9_\-\.]*).finished.json\Z"
)
SKIPPED_RE: Final = re.compile(
    r"\A\d+\.(?P<id>[a-zA-Z][a-zA-Z0-9_\-\.]*).skipped.json\Z"
)
DIGITS = 4


@dataclasses.dataclass(frozen=True)
class Bake:
    project: str
    batch: str
    when: datetime.datetime
    suffix: str
    config_path: str
    configs_files: Sequence[LocalPath]

    def __str__(self) -> str:
        folder = "_".join([self.batch, _dt2str(self.when), self.suffix])
        return f"{self.project}/{folder}"

    @property
    def bake_id(self) -> str:
        return "_".join([self.batch, _dt2str(self.when), self.suffix])


@dataclasses.dataclass(frozen=True)
class Attempt:
    bake: Bake
    when: datetime.datetime
    number: int
    result: JobStatus

    def __str__(self) -> str:
        folder = "_".join([self.bake.batch, _dt2str(self.bake.when), self.bake.suffix])
        return f"{self.bake.project} {folder} #{self.number}"


@dataclasses.dataclass(frozen=True)
class StartedTask:
    attempt: Attempt
    id: FullID
    raw_id: str
    created_at: datetime.datetime
    when: datetime.datetime


@dataclasses.dataclass(frozen=True)
class FinishedTask:
    attempt: Attempt
    id: FullID
    raw_id: str
    when: datetime.datetime
    status: JobStatus
    exit_code: Optional[int]
    created_at: datetime.datetime
    started_at: datetime.datetime
    finished_at: datetime.datetime
    finish_reason: str
    finish_description: str
    outputs: Mapping[str, str]


@dataclasses.dataclass(frozen=True)
class SkippedTask:
    attempt: Attempt
    id: FullID
    when: datetime.datetime


@dataclasses.dataclass(frozen=True)
class ConfigFile:
    path: LocalPath
    content: str


# A storage abstraction
#
# There is a possibility to add Postgres storage class later, for example


class BatchStorage(abc.ABC):
    async def __aenter__(self) -> "BatchStorage":
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    @abc.abstractmethod
    async def close(self) -> None:
        pass

    @abc.abstractmethod
    async def list_bakes(self, project: str) -> AsyncIterator[Bake]:
        # This is here to make this real aiter for type checker
        bake = Bake(
            project="project",
            batch="batch",
            when=datetime.datetime.now(),
            suffix="suffix",
            config_path="config_path",
            configs_files=[],
        )
        yield bake

    @abc.abstractmethod
    async def create_bake(
        self,
        project: str,
        batch: str,
        config_path: str,
        configs: Sequence[ConfigFile],
    ) -> Bake:
        pass

    @abc.abstractmethod
    async def fetch_bake(
        self, project: str, batch: str, when: datetime.datetime, suffix: str
    ) -> Bake:
        pass

    @abc.abstractmethod
    async def fetch_bake_by_id(self, project: str, bake_id: str) -> Bake:
        pass

    @abc.abstractmethod
    async def fetch_configs(self, bake: Bake) -> Sequence[ConfigFile]:
        pass

    @abc.abstractmethod
    async def create_attempt(self, bake: Bake, attempt_no: int) -> Attempt:
        pass

    @abc.abstractmethod
    async def find_attempt(self, bake: Bake, attempt_no: int = -1) -> Attempt:
        pass

    @abc.abstractmethod
    async def fetch_attempt(
        self, attempt: Attempt
    ) -> Tuple[
        Dict[FullID, StartedTask],
        Dict[FullID, FinishedTask],
        Dict[FullID, SkippedTask],
    ]:
        pass

    @abc.abstractmethod
    async def finish_attempt(self, attempt: Attempt, result: JobStatus) -> None:
        pass

    @abc.abstractmethod
    async def start_task(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: FullID,
        descr: JobDescription,
    ) -> StartedTask:
        pass

    @abc.abstractmethod
    async def start_batch_action(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: FullID,
    ) -> StartedTask:
        pass

    @abc.abstractmethod
    async def finish_task(
        self,
        attempt: Attempt,
        task_no: int,
        task: StartedTask,
        descr: JobDescription,
        outputs: Mapping[str, str],
    ) -> FinishedTask:
        pass

    @abc.abstractmethod
    async def finish_batch_action(
        self,
        attempt: Attempt,
        task_no: int,
        task: StartedTask,
        result: DepCtx,
    ) -> FinishedTask:
        pass

    @abc.abstractmethod
    async def skip_task(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: FullID,
    ) -> SkippedTask:
        pass

    @abc.abstractmethod
    async def check_cache(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: FullID,
        ctx: TaskContext,
    ) -> Optional[FinishedTask]:
        pass

    @abc.abstractmethod
    async def write_cache(
        self,
        attempt: Attempt,
        ctx: TaskContext,
        ft: FinishedTask,
    ) -> None:
        pass

    @abc.abstractmethod
    async def clear_cache(self, project: str, batch: Optional[str] = None) -> None:
        pass


class FileSystem(abc.ABC):
    root: URL

    @abstractmethod
    async def stat(self, uri: URL) -> FileStatus:
        pass

    @abstractmethod
    async def ls(self, uri: URL) -> AsyncIterator[FileStatus]:
        yield cast(FileStatus, None)  # For type check

    @abstractmethod
    async def mkdir(
        self, uri: URL, *, parents: bool = False, exist_ok: bool = False
    ) -> None:
        pass

    @abstractmethod
    async def open(self, uri: URL) -> AsyncIterator[bytes]:
        yield b""

    @abstractmethod
    async def create(self, uri: URL, data: bytes) -> None:
        pass

    @abstractmethod
    async def rm(self, uri: URL, *, recursive: bool = False) -> None:
        pass


class LocalFS(FileSystem):
    def __init__(self, path: LocalPath):
        self.root = URL(path.as_uri())

    def _to_path(self, uri: URL) -> LocalPath:
        assert uri.scheme == "file"
        path = uri.path
        # ':' is not supported on Windows
        path = path.replace(":", "-")
        return LocalPath(path)

    def _path_to_fstatus(self, path: LocalPath) -> FileStatus:
        path = path.resolve()
        if path.is_dir():
            fstype = FileStatusType.DIRECTORY
        elif path.is_file():
            fstype = FileStatusType.FILE
        else:
            raise ValueError(f"The {path} is not either file or directory")
        stat = path.stat()
        return FileStatus(
            path=str(path),
            size=stat.st_size,
            type=fstype,
            modification_time=int(stat.st_mtime),
            permission=Action.MANAGE,
            uri=URL(path.as_uri()),
        )

    async def stat(self, uri: URL) -> FileStatus:
        return self._path_to_fstatus(self._to_path(uri))

    async def ls(self, uri: URL) -> AsyncIterator[FileStatus]:
        path = self._to_path(uri)
        for path in path.iterdir():
            yield self._path_to_fstatus(path)

    async def mkdir(
        self, uri: URL, *, parents: bool = False, exist_ok: bool = False
    ) -> None:
        path = self._to_path(uri)
        path.mkdir(parents=parents, exist_ok=exist_ok)

    async def open(self, uri: URL) -> AsyncIterator[bytes]:
        path = self._to_path(uri)
        try:
            yield path.read_bytes()
        except FileNotFoundError:
            raise ValueError

    async def create(self, uri: URL, data: bytes) -> None:
        path = self._to_path(uri)
        path.write_bytes(data)

    async def rm(self, uri: URL, *, recursive: bool = False) -> None:
        path = self._to_path(uri)
        if recursive:
            shutil.rmtree(path)
        else:
            path.unlink()


class NeuroStorageFS(FileSystem):
    root = URL("storage:.flow")

    def __init__(self, client: Client):
        self._client = client

    async def stat(self, uri: URL) -> FileStatus:
        return await self._client.storage.stat(uri)

    def ls(self, uri: URL) -> AsyncIterator[FileStatus]:
        return self._client.storage.ls(uri)

    async def mkdir(
        self, uri: URL, *, parents: bool = False, exist_ok: bool = False
    ) -> None:
        await self._client.storage.mkdir(uri, parents=parents, exist_ok=exist_ok)

    def open(self, uri: URL) -> AsyncIterator[bytes]:
        return self._client.storage.open(uri)

    async def create(self, uri: URL, data: bytes) -> None:
        await self._client.storage.create(uri, data)

    async def rm(self, uri: URL, *, recursive: bool = False) -> None:
        await self._client.storage.rm(uri, recursive=recursive)


class BatchFSStorage(BatchStorage):
    # A storage that uses storage:.flow directory as a database

    # A lack of true atomic operations (and server-side move/rename which prevents
    # overriding the destination) on the storage fs makes the implementation slightly
    # subtle but it's ok.
    #
    # The genuine consistent storage like PostgresSQL-based dedicated Neuro platform
    # service can be added later as a separate implementation that follows the same
    # abstract API.

    # The FS structure:
    # storage:.flow
    # +-- bake_id
    #     +-- configs
    #         +-- project.yml
    #         +-- batch_config.yml
    #         +-- action1_config.yml
    #         +-- dir/action2_config.yml
    #     +-- 00.init.json
    #     +-- 01.attempt
    #         +-- 000.init.json
    #         +-- 001.<task_id>.started.json
    #         +-- 002.<task_id>.finished.json
    #         +-- 999.result.json
    #     +-- 02.attempt
    #         +-- 000.init.json
    #         +-- 001.<task_id>.started.json
    #         +-- 002.<task_id>.finished.json
    #         +-- 999.result.json

    def __init__(self, fs: FileSystem) -> None:
        self._fs = fs

    async def close(self) -> None:
        pass

    async def list_bakes(self, project: str) -> AsyncIterator[Bake]:
        url = self._fs.root / project
        try:
            fs = await self._fs.stat(url)
            if not fs.is_dir():
                raise ValueError(f"{url} is not a directory")
        except ValueError:
            raise ValueError(f"Cannot find remote project {url}")

        async for fs in self._fs.ls(url):
            name = fs.name
            try:
                data = await self._read_json(url / name / "00.init.json")
                yield _bake_from_json(data)
            except (ValueError, LookupError):
                # Not a bake folder, happens by incident
                log.warning("Invalid record %s", url / fs.name)
                continue

    async def create_bake(
        self,
        project: str,
        batch: str,
        config_path: str,
        configs: Sequence[ConfigFile],
    ) -> Bake:
        when = _now()
        bake = Bake(
            project=project,
            batch=batch,
            when=when,
            suffix=secrets.token_hex(3),
            config_path=config_path,
            configs_files=[config.path for config in configs],
        )
        bake_uri = _mk_bake_uri(self._fs, bake)
        await self._fs.mkdir(bake_uri, parents=True)

        # Upload all configs
        configs_dir = bake_uri / "configs"
        await self._fs.mkdir(configs_dir, parents=True)
        for config in configs:
            await self._fs.mkdir(
                configs_dir / str(config.path.parent),
                parents=True,
                exist_ok=True,
            )
            await self._write_file(configs_dir / str(config.path), config.content)

        await self._write_json(bake_uri / "00.init.json", _bake_to_json(bake))
        # TODO: make the bake and the first attempt creation atomic to avoid
        # a (very short) state when a bake exists but an attempt does not.
        # To solve it, create a temporary folder for bake on storage, fill it with
        # 00.init.json and 01.attempt folder with 000.init.json inside,
        # rename the folder to <bake_id>
        await self.create_attempt(bake, 1)
        return bake

    async def fetch_bake(
        self, project: str, batch: str, when: datetime.datetime, suffix: str
    ) -> Bake:
        data = await self._read_json(
            _mk_bake_uri_from_id(self._fs, project, batch, when, suffix)
            / "00.init.json"
        )
        return _bake_from_json(data)

    async def fetch_bake_by_id(self, project: str, bake_id: str) -> Bake:
        url = self._fs.root / project / bake_id
        data = await self._read_json(url / "00.init.json")
        return _bake_from_json(data)

    async def fetch_configs(self, bake: Bake) -> Sequence[ConfigFile]:
        configs_dir_uri = _mk_bake_uri(self._fs, bake) / "configs"
        return [
            ConfigFile(path, await self._read_file(configs_dir_uri / str(path)))
            for path in bake.configs_files
        ]

    async def create_attempt(self, bake: Bake, attempt_no: int) -> Attempt:
        assert 0 < attempt_no < 100, attempt_no
        bake_uri = _mk_bake_uri(self._fs, bake)
        attempt_uri = bake_uri / f"{attempt_no:02d}.attempt"
        await self._fs.mkdir(attempt_uri)
        pre = "0".zfill(DIGITS)
        when = _now()
        ret = Attempt(bake=bake, when=when, number=attempt_no, result=JobStatus.PENDING)
        await self._write_json(attempt_uri / f"{pre}.init.json", _attempt_to_json(ret))
        return ret

    async def find_attempt(self, bake: Bake, attempt_no: int = -1) -> Attempt:
        bake_uri = _mk_bake_uri(self._fs, bake)
        if attempt_no == -1:
            files = set()
            async for fi in self._fs.ls(bake_uri):
                files.add(fi.name)
            for attempt_no in range(99, 0, -1):
                fname = f"{attempt_no:02d}.attempt"
                if fname in files:
                    return await self.find_attempt(bake, attempt_no)
            assert False, "unreachable"
        else:
            assert 0 < attempt_no < 99
            fname = f"{attempt_no:02d}.attempt"
            pre = "0".zfill(DIGITS)
            init_name = f"{pre}.init.json"
            init_data = await self._read_json(bake_uri / fname / init_name)
            pre = "9" * DIGITS
            result_name = f"{pre}.result.json"
            try:
                result_data = await self._read_json(bake_uri / fname / result_name)
            except ValueError:
                result_data = None
            return _attempt_from_json(init_data, result_data)

    async def fetch_attempt(
        self, attempt: Attempt
    ) -> Tuple[
        Dict[FullID, StartedTask],
        Dict[FullID, FinishedTask],
        Dict[FullID, SkippedTask],
    ]:
        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = "0".zfill(DIGITS)
        init_name = f"{pre}.init.json"
        pre = "9" * DIGITS
        result_name = f"{pre}.result.json"
        data = await self._read_json(attempt_url / init_name)
        started = {}
        finished = {}
        skipped = {}
        files = []
        async for fs in self._fs.ls(attempt_url):
            if fs.name == init_name:
                continue
            if fs.name == result_name:
                continue
            files.append(fs.name)

        files.sort()

        for fname in files:
            match = STARTED_RE.match(fname)
            if match:
                data = await self._read_json(attempt_url / fname)
                assert match.group("id") == data["id"]
                full_id = tuple(data["id"].split("."))
                started[full_id] = StartedTask(
                    attempt=attempt,
                    id=full_id,
                    raw_id=data["raw_id"],
                    created_at=datetime.datetime.fromisoformat(data["created_at"]),
                    when=datetime.datetime.fromisoformat(data["when"]),
                )
                continue
            match = FINISHED_RE.match(fname)
            if match:
                data = await self._read_json(attempt_url / fname)
                assert match.group("id") == data["id"]
                full_id = tuple(data["id"].split("."))
                finished[full_id] = FinishedTask(
                    attempt=attempt,
                    id=full_id,
                    raw_id=data["raw_id"],
                    when=datetime.datetime.fromisoformat(data["when"]),
                    status=JobStatus(data["status"]),
                    exit_code=data["exit_code"],
                    created_at=datetime.datetime.fromisoformat(data["created_at"]),
                    started_at=datetime.datetime.fromisoformat(data["started_at"]),
                    finished_at=datetime.datetime.fromisoformat(data["finished_at"]),
                    finish_reason=data["finish_reason"],
                    finish_description=data["finish_description"],
                    outputs=data["outputs"],
                )
                continue
            match = SKIPPED_RE.match(fname)
            if match:
                data = await self._read_json(attempt_url / fname)
                assert match.group("id").split(".") == data["id"]
                full_id = tuple(data["id"].split("."))
                skipped[full_id] = SkippedTask(
                    attempt=attempt,
                    id=full_id,
                    when=datetime.datetime.fromisoformat(data["when"]),
                )
                continue
            raise ValueError(f"Unexpected name {attempt_url / fname}")
        assert finished.keys() <= started.keys()
        return started, finished, skipped

    async def finish_attempt(self, attempt: Attempt, result: JobStatus) -> None:
        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = "9" * DIGITS
        data = {"result": result.value}
        await self._write_json(attempt_url / f"{pre}.result.json", data)

    async def start_task(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: FullID,
        descr: JobDescription,
    ) -> StartedTask:
        assert 0 <= task_no < int("9" * DIGITS) - 1, task_no
        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = str(task_no + 1).zfill(DIGITS)
        assert descr.history.created_at is not None
        ret = StartedTask(
            attempt=attempt,
            id=task_id,
            raw_id=descr.id,
            when=datetime.datetime.now(datetime.timezone.utc),
            created_at=descr.history.created_at,
        )

        data = {
            "id": ".".join(ret.id),
            "raw_id": ret.raw_id,
            "when": ret.when.isoformat(timespec="seconds"),
            "created_at": ret.created_at.isoformat(timespec="seconds"),
        }
        await self._write_json(attempt_url / f"{pre}.{data['id']}.started.json", data)
        return ret

    async def start_batch_action(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: FullID,
    ) -> StartedTask:
        assert 0 <= task_no < int("9" * DIGITS) - 1, task_no
        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = str(task_no + 1).zfill(DIGITS)
        now = datetime.datetime.now(datetime.timezone.utc)
        ret = StartedTask(
            attempt=attempt,
            id=task_id,
            raw_id="",
            when=now,
            created_at=now,
        )

        data = {
            "id": ".".join(ret.id),
            "raw_id": ret.raw_id,
            "when": ret.when.isoformat(timespec="seconds"),
            "created_at": ret.created_at.isoformat(timespec="seconds"),
        }
        await self._write_json(attempt_url / f"{pre}.{data['id']}.started.json", data)
        return ret

    async def finish_task(
        self,
        attempt: Attempt,
        task_no: int,
        task: StartedTask,
        descr: JobDescription,
        outputs: Mapping[str, str],
    ) -> FinishedTask:
        assert task.raw_id == descr.id
        assert task.created_at == descr.history.created_at
        assert descr.history.created_at is not None
        assert descr.history.started_at is not None
        assert descr.history.finished_at is not None
        ret = FinishedTask(
            attempt=attempt,
            id=task.id,
            raw_id=task.raw_id,
            when=datetime.datetime.now(datetime.timezone.utc),
            status=descr.history.status,
            exit_code=descr.history.exit_code,
            created_at=descr.history.created_at,
            started_at=descr.history.started_at,
            finished_at=descr.history.finished_at,
            finish_reason=descr.history.reason,
            finish_description=descr.history.description,
            outputs=outputs,
        )
        await self._write_finish(attempt, task_no, ret)
        return ret

    async def _write_finish(
        self, attempt: Attempt, task_no: int, ft: FinishedTask
    ) -> None:
        assert 0 <= task_no < int("9" * DIGITS) - 1, task_no
        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = str(task_no + 1).zfill(DIGITS)
        data = {
            "id": ".".join(ft.id),
            "raw_id": ft.raw_id,
            "when": ft.when.isoformat(timespec="seconds"),
            "status": ft.status.value,
            "exit_code": ft.exit_code,
            "created_at": ft.created_at.isoformat(timespec="seconds"),
            "started_at": ft.started_at.isoformat(timespec="seconds"),
            "finished_at": ft.finished_at.isoformat(timespec="seconds"),
            "finish_reason": ft.finish_reason,
            "finish_description": ft.finish_description,
            "outputs": ft.outputs,
        }
        await self._write_json(attempt_url / f"{pre}.{data['id']}.finished.json", data)

    async def finish_batch_action(
        self,
        attempt: Attempt,
        task_no: int,
        task: StartedTask,
        result: DepCtx,
    ) -> FinishedTask:
        now = datetime.datetime.now(datetime.timezone.utc)
        assert (
            result.result != TaskStatus.DISABLED
        ), "Finished task cannot have disabled state, use .skip_task() instead"
        status = JobStatus(result.result)
        ret = FinishedTask(
            attempt=attempt,
            id=task.id,
            raw_id="",
            when=now,
            status=status,
            exit_code=None,
            created_at=task.created_at,
            started_at=task.created_at,
            finished_at=now,
            finish_reason="",
            finish_description="",
            outputs=result.outputs,
        )
        await self._write_finish(attempt, task_no, ret)
        return ret

    async def skip_task(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: FullID,
    ) -> SkippedTask:
        assert 0 <= task_no < int("9" * DIGITS) - 1, task_no
        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = str(task_no + 1).zfill(DIGITS)
        ret = SkippedTask(
            attempt=attempt,
            id=task_id,
            when=datetime.datetime.now(datetime.timezone.utc),
        )

        data = {
            "id": ".".join(ret.id),
            "when": ret.when.isoformat(timespec="seconds"),
        }
        await self._write_json(attempt_url / f"{pre}.{data['id']}.skipped.json", data)
        return ret

    async def check_cache(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: FullID,
        ctx: TaskContext,
    ) -> Optional[FinishedTask]:
        cache_strategy = ctx.cache.strategy
        if cache_strategy == ast.CacheStrategy.NONE:
            return None
        assert cache_strategy == ast.CacheStrategy.DEFAULT

        url = _mk_cache_uri(attempt, task_id)

        try:
            data = await self._read_json(url)
        except ValueError:
            # not found
            return None
        ctx_digest = _hash(ctx)

        try:
            when = datetime.datetime.fromisoformat(data["when"])
            now = datetime.datetime.now(datetime.timezone.utc)
            eol = when + datetime.timedelta(ctx.cache.life_span)
            if eol < now:
                return None
            if data["digest"] != ctx_digest:
                return None
            ret = FinishedTask(
                attempt=attempt,
                id=task_id,
                raw_id=data["raw_id"],
                when=datetime.datetime.fromisoformat(data["when"]),
                status=JobStatus(data["status"]),
                exit_code=data["exit_code"],
                created_at=datetime.datetime.fromisoformat(data["created_at"]),
                started_at=datetime.datetime.fromisoformat(data["started_at"]),
                finished_at=datetime.datetime.fromisoformat(data["finished_at"]),
                finish_reason=data["finish_reason"],
                finish_description=data["finish_description"],
                outputs=data["outputs"],
            )
            await self._write_finish(attempt, task_no, ret)
            return ret
        except (KeyError, ValueError, TypeError):
            # something is wrong with stored JSON,
            # e.g. the structure doesn't match the expected schema
            return None

    async def write_cache(
        self,
        attempt: Attempt,
        ctx: TaskContext,
        ft: FinishedTask,
    ) -> None:
        cache_strategy = ctx.cache.strategy
        if cache_strategy == ast.CacheStrategy.NONE:
            return
        if ft.status != JobStatus.SUCCEEDED:
            return

        ctx_digest = _hash(ctx)
        url = _mk_cache_uri(attempt, ft.id)
        assert ft.raw_id is not None, (ft.id, ft.raw_id)

        data = {
            "when": ft.when.isoformat(timespec="seconds"),
            "digest": ctx_digest,
            "raw_id": ft.raw_id,
            "status": ft.status.value,
            "exit_code": ft.exit_code,
            "created_at": ft.created_at.isoformat(timespec="seconds"),
            "started_at": ft.started_at.isoformat(timespec="seconds"),
            "finished_at": ft.finished_at.isoformat(timespec="seconds"),
            "finish_reason": ft.finish_reason,
            "finish_description": ft.finish_description,
            "outputs": ft.outputs,
        }
        try:
            await self._write_json(url, data, overwrite=True)
        except ResourceNotFound:
            await self._fs.mkdir(url.parent, parents=True)
            await self._write_json(url, data, overwrite=True)

    async def clear_cache(self, project: str, batch: Optional[str] = None) -> None:
        await self._fs.rm(_mk_cache_uri2(project, batch), recursive=True)

    async def _read_file(self, url: URL) -> str:
        ret = []
        async for chunk in self._fs.open(url):
            ret.append(chunk)
        return b"".join(ret).decode("utf-8")

    async def _read_json(self, url: URL) -> Any:
        data = await self._read_file(url)
        return json.loads(data)

    async def _write_file(
        self, url: URL, body: str, *, overwrite: bool = False
    ) -> None:
        # TODO: Prevent overriding the target on the storage.
        #
        # It might require platform_storage_api change.
        #
        # There is no clean understanding if the storage can support this strong
        # guarantee at all.
        if not overwrite:
            files = set()
            async for fi in self._fs.ls(url.parent):
                files.add(fi.name)
            if url.name in files:
                raise ValueError(f"File {url} already exists")
        await self._fs.create(url, body.encode("utf-8"))

    async def _write_json(
        self, url: URL, data: Dict[str, Any], *, overwrite: bool = False
    ) -> None:
        if not data.get("when"):
            data["when"] = _dt2str(_now())

        await self._write_file(url, json.dumps(data), overwrite=overwrite)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _dt2str(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _mk_bake_uri_from_id(
    fs: FileSystem, project: str, batch: str, when: datetime.datetime, suffix: str
) -> URL:
    bake_id = "_".join([batch, _dt2str(when), suffix])
    return fs.root / project / bake_id


def _mk_bake_uri(fs: FileSystem, bake: Bake) -> URL:
    return _mk_bake_uri_from_id(fs, bake.project, bake.batch, bake.when, bake.suffix)


def _bake_to_json(bake: Bake) -> Dict[str, Any]:
    return {
        "project": bake.project,
        "batch": bake.batch,
        "when": _dt2str(bake.when),
        "suffix": bake.suffix,
        "config_path": bake.config_path,
        "config_files": [str(path) for path in bake.configs_files],
    }


def _bake_from_json(data: Dict[str, Any]) -> Bake:
    return Bake(
        project=data["project"],
        batch=data["batch"],
        when=datetime.datetime.fromisoformat(data["when"]),
        suffix=data["suffix"],
        config_path=data["config_path"],
        configs_files=[LocalPath(path) for path in data["config_files"]],
    )


def _attempt_to_json(attempt: Attempt) -> Dict[str, Any]:
    return {
        "number": attempt.number,
        "bake": _bake_to_json(attempt.bake),
        "when": _dt2str(attempt.when),
    }


def _attempt_from_json(
    init_data: Dict[str, Any], result_data: Optional[Dict[str, Any]]
) -> Attempt:
    if result_data is not None:
        result = JobStatus(result_data["result"])
    else:
        result = JobStatus.RUNNING
    return Attempt(
        bake=_bake_from_json(init_data["bake"]),
        when=datetime.datetime.fromisoformat(init_data["when"]),
        number=init_data["number"],
        result=result,
    )


def _mk_cache_uri(attempt: Attempt, task_id: FullID) -> URL:
    return _mk_cache_uri2(attempt.bake.project, attempt.bake.batch) / (
        ".".join(task_id) + ".json"
    )


def _mk_cache_uri2(project: str, batch: Optional[str]) -> URL:
    ret = URL("storage:.flow") / project / ".cache"
    if batch:
        ret /= batch
    return ret


def _hash(val: Any) -> str:
    hasher = hashlib.new("sha256")
    data = json.dumps(val, sort_keys=True, default=_ctx_default)
    hasher.update(data.encode("utf-8"))
    return hasher.hexdigest()


def _ctx_default(val: Any) -> Any:
    if isinstance(val, BaseContext):
        ret: Dict[str, Any] = {
            "env": val.env,
            "tags": val.tags,
        }
        if isinstance(val, ActionContext):
            ret.update(
                {
                    "inputs": val.inputs,
                }
            )
        elif isinstance(val, TaskContext):
            ret.update(
                {
                    "needs": val.needs,
                    "matrix": val.matrix,
                    "strategy": val.strategy,
                    "task": val.task,
                }
            )
        return ret
    elif dataclasses.is_dataclass(val):
        return dataclasses.asdict(val)
    elif isinstance(val, enum.Enum):
        return val.value
    elif isinstance(val, RemotePath):
        return str(val)
    elif isinstance(val, collections.abc.Set):
        return sorted(val)
    else:
        raise TypeError(f"Cannot dump {val!r}")
