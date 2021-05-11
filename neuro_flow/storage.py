import dataclasses

import abc
import datetime
import hashlib
import json
import logging
import re
import secrets
import shutil
import sys
from abc import abstractmethod
from neuro_sdk import (
    Action,
    Client,
    FileStatus,
    FileStatusType,
    JobDescription,
    ResourceNotFound,
)
from operator import attrgetter
from types import TracebackType
from typing import (
    AbstractSet,
    Any,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    cast,
)
from typing_extensions import Final, TypedDict
from yarl import URL

from neuro_flow.types import LocalPath

from .config_loader import ConfigFile
from .context import DepCtx, JobMeta
from .types import FullID, TaskStatus


if sys.version_info < (3, 7):
    from backports.datetime_fromisoformat import MonkeyPatch

    MonkeyPatch.patch_fromisoformat()


log = logging.getLogger(__name__)

STARTED_RE: Final = re.compile(r"\A(?P<id>[a-zA-Z][a-zA-Z0-9_\-\.]*).started.json\Z")
FINISHED_RE: Final = re.compile(r"\A(?P<id>[a-zA-Z][a-zA-Z0-9_\-\.]*).finished.json\Z")
DIGITS = 4


@dataclasses.dataclass(frozen=True)
class Project:
    id: str
    name: str
    owner: str
    cluster: str


@dataclasses.dataclass(frozen=True)
class Live:
    project: str
    when: datetime.datetime
    jobs: Sequence["Job"]


@dataclasses.dataclass(frozen=True)
class Job:
    # Job has no 'when' and reference to 'live'
    # because it always exists as a part of live.jobs sequence.
    id: str
    multi: bool
    tags: Sequence[str]


@dataclasses.dataclass(frozen=True)
class Bake:
    project: str
    batch: str
    when: datetime.datetime
    suffix: str
    # prefix -> { id -> deps }
    graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]]
    params: Optional[Mapping[str, str]]
    name: Optional[str]

    tags: Sequence[str]

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
    result: TaskStatus
    executor_id: Optional[str]

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
    status: TaskStatus
    created_at: datetime.datetime
    started_at: datetime.datetime
    finished_at: datetime.datetime
    outputs: Mapping[str, str]
    state: Mapping[str, str]


# A storage abstraction
#
# There is a possibility to add Postgres storage class later, for example


class Storage(abc.ABC):
    async def __aenter__(self) -> "Storage":
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
    async def ensure_project(
        self, name: str, owner: Optional[str] = None, cluster: Optional[str] = None
    ) -> Project:
        pass

    # TODO: implement fetch_live() counterpart
    @abc.abstractmethod
    async def write_live(self, project: str, jobs: Iterable[JobMeta]) -> Live:
        pass

    @abc.abstractmethod
    async def list_bakes(
        self, project: str, tags: Optional[AbstractSet[str]] = None
    ) -> AsyncIterator[Bake]:
        # This is here to make this real aiter for type checker
        bake = Bake(
            project="project",
            batch="batch",
            when=datetime.datetime.now(),
            suffix="suffix",
            graphs={},
            params={},
            name=None,
            tags=(),
        )
        yield bake

    @abc.abstractmethod
    async def create_bake(
        self,
        project: str,
        batch: str,
        configs_meta: Mapping[str, Any],
        configs: Sequence[ConfigFile],
        graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]],
        params: Optional[Mapping[str, str]],
        name: Optional[str],
        tags: Sequence[str] = (),
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
    async def fetch_bake_by_name(self, project: str, bake_name: str) -> Bake:
        pass

    @abc.abstractmethod
    async def fetch_configs_meta(self, bake: Bake) -> Mapping[str, Any]:
        pass

    @abc.abstractmethod
    async def fetch_config(self, bake: Bake, filename: str) -> str:
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
    ) -> Tuple[Dict[FullID, StartedTask], Dict[FullID, FinishedTask]]:
        pass

    @abc.abstractmethod
    async def store_executor_id(self, attempt: Attempt, executor_id: str) -> None:
        pass

    @abc.abstractmethod
    async def finish_attempt(self, attempt: Attempt, result: TaskStatus) -> None:
        pass

    async def start_task(
        self,
        attempt: Attempt,
        task_id: FullID,
        descr: JobDescription,
    ) -> StartedTask:
        assert descr.history.created_at is not None
        ret = StartedTask(
            attempt=attempt,
            id=task_id,
            raw_id=descr.id or "",
            when=datetime.datetime.now(datetime.timezone.utc),
            created_at=descr.history.created_at,
        )

        await self.write_start(ret)
        return ret

    async def start_action(
        self,
        attempt: Attempt,
        task_id: FullID,
    ) -> StartedTask:
        now = datetime.datetime.now(datetime.timezone.utc)
        ret = StartedTask(
            attempt=attempt,
            id=task_id,
            raw_id="",
            when=now,
            created_at=now,
        )
        await self.write_start(ret)
        return ret

    async def finish_task(
        self,
        attempt: Attempt,
        task: StartedTask,
        descr: JobDescription,
        outputs: Mapping[str, str],
        state: Mapping[str, str],
    ) -> FinishedTask:
        assert task.raw_id == descr.id
        assert task.created_at == descr.history.created_at
        assert descr.history.created_at is not None
        assert descr.history.started_at is not None
        assert descr.history.finished_at is not None
        ret = FinishedTask(
            attempt=attempt,
            id=task.id,
            raw_id=task.raw_id or "",
            when=datetime.datetime.now(datetime.timezone.utc),
            status=TaskStatus(descr.history.status),
            created_at=descr.history.created_at,
            started_at=descr.history.started_at,
            finished_at=descr.history.finished_at,
            outputs=outputs,
            state=state,
        )
        await self.write_finish(ret)
        return ret

    async def finish_action(
        self,
        attempt: Attempt,
        task: StartedTask,
        result: DepCtx,
    ) -> FinishedTask:
        now = datetime.datetime.now(datetime.timezone.utc)
        assert result.result != TaskStatus.SKIPPED, (
            "Finished task cannot be disabled (it is already started),"
            " use .skip_task() instead"
        )
        status = TaskStatus(result.result)
        ret = FinishedTask(
            attempt=attempt,
            id=task.id,
            raw_id="",
            when=now,
            status=status,
            created_at=task.created_at,
            started_at=task.created_at,
            finished_at=now,
            outputs=result.outputs,
            state={},
        )
        await self.write_finish(ret)
        return ret

    async def skip_task(
        self,
        attempt: Attempt,
        task_id: FullID,
    ) -> Tuple[StartedTask, FinishedTask]:
        now = datetime.datetime.now(datetime.timezone.utc)

        st = StartedTask(
            attempt=attempt,
            id=task_id,
            raw_id="",
            when=now,
            created_at=now,
        )
        await self.write_start(st)

        ft = FinishedTask(
            attempt=attempt,
            id=task_id,
            raw_id="",
            when=now,
            status=TaskStatus.SKIPPED,
            created_at=now,
            started_at=now,
            finished_at=now,
            outputs={},
            state={},
        )
        await self.write_finish(ft)
        return st, ft

    @abc.abstractmethod
    async def write_start(
        self,
        task: StartedTask,
    ) -> None:
        pass

    @abc.abstractmethod
    async def write_finish(
        self,
        task: FinishedTask,
    ) -> None:
        pass

    @abc.abstractmethod
    async def check_cache(
        self,
        attempt: Attempt,
        task_id: FullID,
        caching_key: str,
        life_span: datetime.timedelta,
    ) -> Optional[FinishedTask]:
        pass

    @abc.abstractmethod
    async def write_cache(
        self,
        attempt: Attempt,
        ft: FinishedTask,
        caching_key: str,
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
        path.parent.mkdir(parents=True, exist_ok=True)
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


class FSStorage(Storage):
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
    #  +-- live.json

    def __init__(self, fs: FileSystem) -> None:
        self._fs = fs

    async def close(self) -> None:
        pass

    async def ensure_project(
        self, name: str, owner: Optional[str] = None, cluster: Optional[str] = None
    ) -> Project:
        return Project(id=name, name=name, owner=owner or "", cluster=cluster or "")

    async def write_live(self, project: str, jobs: Iterable[JobMeta]) -> Live:
        when = _now()
        live = Live(
            project=project,
            when=when,
            jobs=sorted(
                [
                    Job(id=job.id, multi=job.multi, tags=sorted(job.tags))
                    for job in jobs
                ],
                key=attrgetter("id"),
            ),
        )
        prj_uri = self._fs.root / project
        await self._fs.mkdir(prj_uri, parents=True, exist_ok=True)
        url = prj_uri / "live.json"
        await self._write_json(url, _live_to_json(live), overwrite=True)
        return live

    async def list_bakes(
        self, project: str, tags: Optional[AbstractSet[str]] = None
    ) -> AsyncIterator[Bake]:
        url = self._fs.root / project
        try:
            fs = await self._fs.stat(url)
            if not fs.is_dir():
                raise ValueError(f"{url} is not a directory")
        except ValueError:
            raise ValueError(f"Cannot find remote project {url}")

        async for fs in self._fs.ls(url):
            name = fs.name
            if name.startswith("."):
                # Ignore hidden names
                continue
            if not fs.is_dir():
                # Ignore files, bake is always a folder
                continue
            try:
                data = await self._read_json(url / name / "00.init.json")
                bake = _bake_from_json(data)
                if tags is not None and not set(bake.tags).issuperset(tags):
                    continue
                yield bake
            except (ValueError, LookupError):
                # Not a bake folder, happens by incident
                log.warning("Invalid record %s", url / fs.name)
                continue

    async def create_bake(
        self,
        project: str,
        batch: str,
        configs_meta: Mapping[str, Any],
        configs: Sequence[ConfigFile],
        graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]],
        params: Optional[Mapping[str, str]],
        name: Optional[str],
        tags: Sequence[str] = (),
    ) -> Bake:
        when = _now()
        bake = Bake(
            project=project,
            batch=batch,
            when=when,
            suffix=secrets.token_hex(3),
            graphs=graphs,
            params=params,
            name=name,
            tags=tags,
        )
        bake_uri = _mk_bake_uri(self._fs, bake)
        await self._fs.mkdir(bake_uri, parents=True)

        # Upload all configs
        await self._write_file(bake_uri / "configs_meta.json", json.dumps(configs_meta))
        configs_dir = bake_uri / "configs"
        await self._fs.mkdir(configs_dir)
        for config in configs:
            await self._write_file(configs_dir / config.filename, config.content)

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

    async def fetch_bake_by_name(self, project: str, name: str) -> Bake:
        candidate: Optional[Tuple[Bake, datetime.datetime]] = None
        async for bake in self.list_bakes(project):
            if bake.name != name:
                continue
            if not candidate or candidate[1] < bake.when:
                candidate = (bake, bake.when)
        if candidate is None:
            raise ResourceNotFound
        return candidate[0]

    async def fetch_configs_meta(self, bake: Bake) -> Mapping[str, Any]:
        ret = await self._read_json(_mk_bake_uri(self._fs, bake) / "configs_meta.json")
        assert isinstance(ret, dict)
        return cast(Mapping[str, Any], ret)

    async def fetch_config(self, bake: Bake, filename: str) -> str:
        return await self._read_file(
            _mk_bake_uri(self._fs, bake) / "configs" / filename
        )

    async def create_attempt(self, bake: Bake, attempt_no: int) -> Attempt:
        assert 0 < attempt_no < 100, attempt_no
        bake_uri = _mk_bake_uri(self._fs, bake)
        attempt_uri = bake_uri / f"{attempt_no:02d}.attempt"
        await self._fs.mkdir(attempt_uri)
        pre = "0".zfill(DIGITS)
        when = _now()
        ret = Attempt(
            bake=bake,
            when=when,
            number=attempt_no,
            result=TaskStatus.PENDING,
            executor_id=None,
        )
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
    ) -> Tuple[Dict[FullID, StartedTask], Dict[FullID, FinishedTask]]:
        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = "0".zfill(DIGITS)
        init_name = f"{pre}.init.json"
        pre = "9" * DIGITS
        result_name = f"{pre}.result.json"
        data = await self._read_json(attempt_url / init_name)
        started = {}
        finished = {}
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
                full_id = _id_from_json(data["id"])

                started[full_id] = StartedTask(
                    attempt=attempt,
                    id=full_id,
                    raw_id=data["raw_id"] or "",
                    created_at=datetime.datetime.fromisoformat(data["created_at"]),
                    when=datetime.datetime.fromisoformat(data["when"]),
                )
                continue
            match = FINISHED_RE.match(fname)
            if match:
                data = await self._read_json(attempt_url / fname)
                assert match.group("id") == data["id"]
                full_id = _id_from_json(data["id"])
                finished[full_id] = FinishedTask(
                    attempt=attempt,
                    id=full_id,
                    raw_id=data["raw_id"] or "",
                    when=datetime.datetime.fromisoformat(data["when"]),
                    status=TaskStatus(data["status"]),
                    created_at=datetime.datetime.fromisoformat(data["created_at"]),
                    started_at=datetime.datetime.fromisoformat(data["started_at"]),
                    finished_at=datetime.datetime.fromisoformat(data["finished_at"]),
                    outputs=data["outputs"],
                    state=data["state"],
                )
                continue
            raise ValueError(f"Unexpected name {attempt_url / fname}")
        assert finished.keys() <= started.keys()
        return started, finished

    async def store_executor_id(self, attempt: Attempt, executor_id: str) -> None:
        pass  # Noop for FS based storage

    async def finish_attempt(self, attempt: Attempt, result: TaskStatus) -> None:
        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = "9" * DIGITS
        data = {"result": result.value}
        await self._write_json(attempt_url / f"{pre}.result.json", data)

    async def write_start(self, st: StartedTask) -> None:
        bake_uri = _mk_bake_uri(self._fs, st.attempt.bake)
        attempt_url = bake_uri / f"{st.attempt.number:02d}.attempt"

        data = {
            "id": _id_to_json(st.id),
            "raw_id": st.raw_id or "",
            "when": st.when.isoformat(),
            "created_at": st.created_at.isoformat(),
        }
        await self._write_json(attempt_url / f"{data['id']}.started.json", data)

    async def write_finish(self, ft: FinishedTask) -> None:
        bake_uri = _mk_bake_uri(self._fs, ft.attempt.bake)
        attempt_url = bake_uri / f"{ft.attempt.number:02d}.attempt"
        data = {
            "id": _id_to_json(ft.id),
            "raw_id": ft.raw_id or "",
            "when": ft.when.isoformat(),
            "status": ft.status.value,
            "exit_code": None,
            "created_at": ft.created_at.isoformat(),
            "started_at": ft.started_at.isoformat(),
            "finished_at": ft.finished_at.isoformat(),
            "finish_reason": "",
            "finish_description": "",
            "outputs": ft.outputs,
            "state": ft.state,
        }
        await self._write_json(attempt_url / f"{data['id']}.finished.json", data)

    async def check_cache(
        self,
        attempt: Attempt,
        task_id: FullID,
        caching_key: str,
        life_span: datetime.timedelta,
    ) -> Optional[FinishedTask]:

        url = _mk_cache_uri(self._fs, attempt, task_id)

        try:
            data = await self._read_json(url)
        except ValueError:
            # not found
            return None

        try:
            when = datetime.datetime.fromisoformat(data["when"])
            now = datetime.datetime.now(datetime.timezone.utc)
            eol = when + life_span
            if eol < now:
                return None
            if data["caching_key"] != caching_key:
                return None
            st = StartedTask(
                attempt=attempt,
                id=task_id,
                raw_id=data["raw_id"] or "",
                when=datetime.datetime.fromisoformat(data["when"]),
                created_at=datetime.datetime.fromisoformat(data["created_at"]),
            )
            await self.write_start(st)
            ft = FinishedTask(
                attempt=attempt,
                id=task_id,
                raw_id=data["raw_id"] or "",
                when=datetime.datetime.fromisoformat(data["when"]),
                status=TaskStatus.CACHED,
                created_at=datetime.datetime.fromisoformat(data["created_at"]),
                started_at=datetime.datetime.fromisoformat(data["started_at"]),
                finished_at=datetime.datetime.fromisoformat(data["finished_at"]),
                outputs=data["outputs"],
                state=data["state"],
            )
            await self.write_finish(ft)
            return ft
        except (KeyError, ValueError, TypeError):
            # something is wrong with stored JSON,
            # e.g. the structure doesn't match the expected schema
            return None

    async def write_cache(
        self,
        attempt: Attempt,
        ft: FinishedTask,
        caching_key: str,
    ) -> None:
        url = _mk_cache_uri(self._fs, attempt, ft.id)
        assert ft.raw_id is not None, (ft.id, ft.raw_id)

        data = {
            "when": ft.when.isoformat(),
            "caching_key": caching_key,
            "raw_id": ft.raw_id or "",
            "status": ft.status.value,
            "exit_code": None,
            "created_at": ft.created_at.isoformat(),
            "started_at": ft.started_at.isoformat(),
            "finished_at": ft.finished_at.isoformat(),
            "finish_reason": "",
            "finish_description": "",
            "outputs": ft.outputs,
            "state": ft.state,
        }
        try:
            await self._write_json(url, data, overwrite=True)
        except ResourceNotFound:
            await self._fs.mkdir(url.parent, parents=True)
            await self._write_json(url, data, overwrite=True)

    async def clear_cache(self, project: str, batch: Optional[str] = None) -> None:
        await self._fs.rm(_mk_cache_uri2(self._fs, project, batch), recursive=True)

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
            data["when"] = _now().isoformat()

        await self._write_file(url, json.dumps(data), overwrite=overwrite)


class APIStorage(Storage):
    # A storage that uses neuro-flow-api server as a storage
    # https://dev.neu.ro

    def __init__(self, client: Client, fs: FileSystem) -> None:
        self._core = client._core
        self._config = client.config
        # https://dev.neu.ro/api/v1 two levels up
        self._base_url = client.config.api_url.parent.parent

        self._fs = fs

        self._projects_cache: Dict[str, Project] = {}
        self._bakes_cache: Dict[str, Dict[str, Any]] = {}
        self._attempts_cache: Dict[str, Dict[str, Any]] = {}

    async def close(self) -> None:
        pass

    async def ensure_project(
        self,
        name: str,
        owner: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> Project:
        if cluster is None:
            cluster = self._config.cluster_name
        try:
            prj = await self._get_project(name, cluster)
            assert (
                prj.cluster == cluster
            ), f"cluster mismatch, {prj.cluster} != {cluster}"
        except ResourceNotFound:
            projects_url = self._base_url / "api/v1/flow/projects"
            auth = await self._config._api_auth()
            async with self._core.request(
                "POST",
                projects_url,
                json={"name": name, "cluster": cluster},
                auth=auth,
            ) as resp:
                payload = await resp.json()
                prj = Project(
                    id=payload["id"],
                    name=payload["name"],
                    owner=payload["owner"],
                    cluster=payload["cluster"],
                )
            self._projects_cache[name] = prj
        return prj

    async def _get_project(
        self, project: str, cluster: Optional[str] = None
    ) -> Project:
        if cluster is None:
            cluster = self._config.cluster_name
        prj = self._projects_cache.get(project)
        if prj is not None and prj.cluster == cluster:
            return prj
        projects_url = self._base_url / "api/v1/flow/projects"
        auth = await self._config._api_auth()
        async with self._core.request(
            "GET",
            projects_url / "by_name",
            params={"name": project, "cluster": cluster},
            auth=auth,
        ) as resp:
            payload = await resp.json()
            prj = Project(
                id=payload["id"],
                name=payload["name"],
                owner=payload["owner"],
                cluster=payload["cluster"],
            )
            self._projects_cache[prj.name] = prj
            return prj

    async def write_live(self, project: str, jobs: Iterable[JobMeta]) -> Live:
        prj = await self._get_project(project)
        jobs_data = sorted(
            [Job(id=job.id, multi=job.multi, tags=sorted(job.tags)) for job in jobs],
            key=attrgetter("id"),
        )
        auth = await self._config._api_auth()
        for job in jobs_data:
            async with self._core.request(
                "PUT",
                url=self._base_url / "api/v1/flow/live_jobs/replace",
                json={
                    "project_id": prj.id,
                    "yaml_id": job.id,
                    "multi": job.multi,
                    "tags": job.tags,
                },
                auth=auth,
            ) as resp:
                await resp.json()

        when = _now()
        live = Live(project=project, when=when, jobs=jobs_data)
        prj_uri = self._fs.root / project
        await self._fs.mkdir(prj_uri, parents=True, exist_ok=True)
        url = prj_uri / "live.json"
        await self._write_json(url, _live_to_json(live), overwrite=True)
        return live

    async def list_bakes(
        self, project: str, tags: Optional[AbstractSet[str]] = None
    ) -> AsyncIterator[Bake]:
        prj = await self._get_project(project)
        url = self._base_url / "api/v1/flow/bakes"
        auth = await self._config._api_auth()

        params = [("project_id", prj.id)]
        if tags is not None:
            params += [("tags", tag) for tag in tags]

        async with self._core.request(
            "GET",
            url,
            params=params,
            headers={
                "Accept": "application/x-ndjson",
            },
            auth=auth,
        ) as resp:
            async for line in resp.content:
                bake_data = json.loads(line)
                bake = _bake_from_api_json(prj, bake_data)
                self._bakes_cache[bake_data["id"]] = bake_data
                yield bake

    async def create_bake(
        self,
        project: str,
        batch: str,
        configs_meta: Mapping[str, Any],
        configs: Sequence[ConfigFile],
        graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]],
        params: Optional[Mapping[str, str]],
        name: Optional[str],
        tags: Sequence[str] = (),
        *,
        when: Optional[datetime.datetime] = None,
    ) -> Bake:
        prj = await self._get_project(project)
        gr = {}
        for k1, v1 in graphs.items():
            subgr = {}
            for k2, v2 in v1.items():
                subgr[_id_to_json(k2)] = [_id_to_json(it) for it in v2]
            gr[_id_to_json(k1)] = subgr
        auth = await self._config._api_auth()

        bake_payload = {
            "project_id": prj.id,
            "batch": batch,
            "graphs": gr,
            "params": params,
            "name": name,
            "tags": tags,
        }
        if when is not None:
            bake_payload["created_at"] = _dt2str(when)

        async with self._core.request(
            "POST",
            url=self._base_url / "api/v1/flow/bakes",
            json=bake_payload,
            auth=auth,
        ) as resp:
            bake_data = await resp.json()

        bake = _bake_from_api_json(prj, bake_data)
        self._bakes_cache[bake_data["id"]] = bake_data
        bake_uri = _mk_bake_uri(self._fs, bake)
        await self._fs.mkdir(bake_uri, parents=True)

        # Upload all configs
        await self._write_file(bake_uri / "configs_meta.json", json.dumps(configs_meta))
        configs_dir = bake_uri / "configs"
        await self._fs.mkdir(configs_dir)

        real_meta = {
            "workspace": configs_meta["workspace"],
            "flow_config_id": None,
            "project_config_id": None,
            "action_config_ids": {},
        }
        flow_config_meta = configs_meta["flow_config"]
        project_config_meta = configs_meta.get("project_config")

        for config in configs:
            await self._write_file(configs_dir / config.filename, config.content)
            filename = config.filename
            if filename == flow_config_meta["storage_filename"]:
                filename = flow_config_meta["real_name"]
                real_meta["flow_config_id"] = await self._write_config(
                    bake_data["id"], filename, config.content
                )
            elif (
                project_config_meta is not None
                and filename == project_config_meta["storage_filename"]
            ):
                filename = project_config_meta["real_name"]
                real_meta["project_config_id"] = await self._write_config(
                    bake_data["id"], filename, config.content
                )
            else:
                for key, action_meta in configs_meta["action_configs"].items():
                    if filename == action_meta["storage_filename"]:
                        filename == action_meta["real_name"]
                        real_meta["action_config_ids"][key] = await self._write_config(
                            bake_data["id"], filename, config.content
                        )
                        break

        await self._write_json(bake_uri / "00.init.json", _bake_to_json(bake))
        await self._create_attempt(bake, 1, real_meta, when)
        return bake

    async def fetch_bake(
        self, project: str, batch: str, when: datetime.datetime, suffix: str
    ) -> Bake:
        prj = await self._get_project(project)
        rounded_when = _dt2str(when)
        for bake_data in self._bakes_cache.values():
            rounded = _dt2str(datetime.datetime.fromisoformat(bake_data["created_at"]))
            if (
                bake_data["project_id"] == project
                and bake_data["batch"] == batch
                and rounded == rounded_when
            ):
                return _bake_from_api_json(prj, bake_data)

        async for bake in self.list_bakes(project):
            if bake.batch == batch and _dt2str(bake.when) == rounded_when:
                return bake

        raise ResourceNotFound

    async def fetch_bake_by_id(self, project: str, bake_id: str) -> Bake:
        batch, whenstr, suffix = bake_id.split("_")
        when = datetime.datetime.fromisoformat(whenstr)

        return await self.fetch_bake(project, batch, when, "")

    async def fetch_bake_by_name(self, project: str, name: str) -> Bake:
        prj = await self._get_project(project)
        url = self._base_url / "api/v1/flow/bakes/by_name"
        auth = await self._config._api_auth()
        async with self._core.request(
            "GET",
            url,
            params={"project_id": prj.id, "name": name},
            auth=auth,
        ) as resp:
            bake_data = await resp.json()
            bake = _bake_from_api_json(prj, bake_data)
            self._bakes_cache[bake_data["id"]] = bake_data
            return bake

    async def _find_bake_data(self, bake: Bake) -> Dict[str, Any]:
        # refresh cache if needed
        await self.fetch_bake(bake.project, bake.batch, bake.when, bake.suffix)
        when_str = _dt2str(bake.when)
        for bake_data in self._bakes_cache.values():
            rounded = _dt2str(datetime.datetime.fromisoformat(bake_data["created_at"]))
            prj = await self._get_project(bake.project)
            if (
                bake_data["project_id"] == prj.id
                and bake_data["batch"] == bake.batch
                and rounded == when_str
            ):
                return bake_data
        raise ValueError(f"Not found: {bake}")

    async def fetch_configs_meta(self, bake: Bake) -> Mapping[str, Any]:
        attempt_data = await self._find_attempt_data(bake, -1)
        meta = attempt_data["configs_meta"]
        assert isinstance(meta, dict)
        flow_config = await self._get_config(meta["flow_config_id"])
        ret = {
            "workspace": meta["workspace"],
            "flow_config": {
                "storage_filename": meta["flow_config_id"],
                "real_name": flow_config["filename"],
            },
            "project_config": None,
            "action_configs": {},
        }
        prj_meta = meta["project_config_id"]
        if prj_meta is not None:
            project_config = await self._get_config(prj_meta)
            ret["project_config"] = {
                "storage_filename": prj_meta,
                "real_name": project_config["filename"],
            }
        for key, val in meta["action_config_ids"].items():
            cfg = await self._get_config(val)
            ret["action_configs"][key] = {
                "storage_filename": val,
                "real_name": cfg["filename"],
            }
        return cast(Mapping[str, Any], ret)

    async def _get_config(self, config_id: str) -> Dict[str, Any]:
        url = self._base_url / "api/v1/flow/config_files" / config_id
        auth = await self._config._api_auth()
        async with self._core.request(
            "GET",
            url,
            auth=auth,
        ) as resp:
            payload = await resp.json()
            return cast(Dict[str, Any], payload)

    async def fetch_config(self, bake: Bake, filename: str) -> str:
        # filename is config id actually
        ret = await self._get_config(filename)
        return str(ret["content"])

    async def _create_attempt(
        self,
        bake: Bake,
        attempt_no: int,
        configs_meta: Mapping[str, Any],
        when: Optional[datetime.datetime] = None,
    ) -> Attempt:
        bake_data = await self._find_bake_data(bake)

        assert 0 < attempt_no < 100, attempt_no
        url = self._base_url / "api/v1/flow/attempts"
        auth = await self._config._api_auth()

        attempt_data = {
            "bake_id": bake_data["id"],
            "number": attempt_no,
            "result": "pending",
            "configs_meta": configs_meta,
        }
        if when is not None:
            attempt_data["created_at"] = _dt2str(when)

        async with self._core.request(
            "POST",
            url,
            json=attempt_data,
            auth=auth,
        ) as resp:
            attempt_data = await resp.json()

        self._attempts_cache[attempt_data["id"]] = attempt_data

        bake_uri = _mk_bake_uri(self._fs, bake)
        attempt_uri = bake_uri / f"{attempt_no:02d}.attempt"
        await self._fs.mkdir(attempt_uri)
        pre = "0".zfill(DIGITS)
        ret = _attempt_from_api_json(bake, attempt_data)
        await self._write_json(attempt_uri / f"{pre}.init.json", _attempt_to_json(ret))
        return ret

    async def create_attempt(
        self,
        bake: Bake,
        attempt_no: int,
        *,
        when: Optional[datetime.datetime] = None,
    ) -> Attempt:
        bake_data = await self._find_bake_data(bake)
        assert attempt_no > 1
        url = self._base_url / "api/v1/flow/attempts/by_number"
        auth = await self._config._api_auth()
        async with self._core.request(
            "GET",
            url,
            params={
                "bake_id": bake_data["id"],
                "number": attempt_no - 1,
            },
            auth=auth,
        ) as resp:
            prev_attempt_data = await resp.json()
        return await self._create_attempt(
            bake, attempt_no, prev_attempt_data["configs_meta"], when
        )

    async def _find_attempt_data(
        self, bake: Bake, attempt_no: int = -1
    ) -> Dict[str, Any]:
        bake_data = await self._find_bake_data(bake)

        for attempt_data in self._attempts_cache.values():
            if (
                attempt_data["bake_id"] == bake_data["id"]
                and attempt_data["number"] == attempt_no
            ):
                return attempt_data

        assert attempt_no == -1 or 0 < attempt_no < 99
        url = self._base_url / "api/v1/flow/attempts/by_number"
        auth = await self._config._api_auth()
        async with self._core.request(
            "GET",
            url,
            params={
                "bake_id": bake_data["id"],
                "number": attempt_no,
            },
            auth=auth,
        ) as resp:
            attempt_data = await resp.json()
            self._attempts_cache[attempt_data["id"]] = attempt_data
            return attempt_data

    async def find_attempt(self, bake: Bake, attempt_no: int = -1) -> Attempt:
        attempt_data = await self._find_attempt_data(bake, attempt_no)
        return _attempt_from_api_json(bake, attempt_data)

    async def fetch_attempt(
        self, attempt: Attempt
    ) -> Tuple[Dict[FullID, StartedTask], Dict[FullID, FinishedTask]]:
        started = {}
        finished = {}

        attempt_data = await self._find_attempt_data(attempt.bake, attempt.number)
        url = self._base_url / "api/v1/flow/tasks"
        auth = await self._config._api_auth()

        async with self._core.request(
            "GET",
            url,
            params={"attempt_id": attempt_data["id"]},
            headers={
                "Accept": "application/x-ndjson",
            },
            auth=auth,
        ) as resp:
            async for line in resp.content:
                task_data = json.loads(line)
                full_id = _id_from_json(task_data["yaml_id"])
                statuses = _parse_statuses(task_data["statuses"])
                status = statuses[-1]["status"]

                started[full_id] = StartedTask(
                    attempt=attempt,
                    id=full_id,
                    raw_id=task_data["raw_id"] or "",
                    created_at=statuses[0]["created_at"],
                    when=statuses[-1]["created_at"],
                )
                if status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    finished[full_id] = FinishedTask(
                        attempt=attempt,
                        id=full_id,
                        raw_id=task_data["raw_id"] or "",
                        when=statuses[-1]["created_at"],
                        status=status,
                        created_at=statuses[0]["created_at"],
                        started_at=_find_started_at(statuses),
                        finished_at=_find_finished_at(statuses),
                        outputs=task_data["outputs"],
                        state=task_data["state"],
                    )
        assert finished.keys() <= started.keys()
        return started, finished

    async def store_executor_id(self, attempt: Attempt, executor_id: str) -> None:
        attempt_data = await self._find_attempt_data(attempt.bake, attempt.number)
        auth = await self._config._api_auth()
        url = self._base_url / "api/v1/flow/attempts/replace"
        async with self._core.request(
            "PUT",
            url,
            json={
                "bake_id": attempt_data["bake_id"],
                "number": attempt_data["number"],
                "result": attempt_data["result"],
                "configs_meta": attempt_data["configs_meta"],
                "executor_id": executor_id,
            },
            auth=auth,
        ) as resp:
            await resp.json()
            self._attempts_cache[attempt_data["id"]]["executor_id"] = executor_id

    async def finish_attempt(self, attempt: Attempt, result: TaskStatus) -> None:
        attempt_data = await self._find_attempt_data(attempt.bake, attempt.number)
        auth = await self._config._api_auth()
        url = self._base_url / "api/v1/flow/attempts/replace"
        async with self._core.request(
            "PUT",
            url,
            json={
                "bake_id": attempt_data["bake_id"],
                "number": attempt_data["number"],
                "result": result.value,
                "configs_meta": attempt_data["configs_meta"],
                "executor_id": attempt_data["executor_id"],
            },
            auth=auth,
        ) as resp:
            await resp.json()
            self._attempts_cache[attempt_data["id"]]["result"] = result.value

        bake_uri = _mk_bake_uri(self._fs, attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        pre = "9" * DIGITS
        data = {"result": result.value}
        await self._write_json(attempt_url / f"{pre}.result.json", data)

    async def write_start(self, st: StartedTask) -> None:
        attempt_data = await self._find_attempt_data(st.attempt.bake, st.attempt.number)
        auth = await self._config._api_auth()
        async with self._core.request(
            "POST",
            self._base_url / "api/v1/flow/tasks",
            json={
                "yaml_id": _id_to_json(st.id),
                "attempt_id": attempt_data["id"],
                "raw_id": st.raw_id or "",
                "outputs": {},
                "state": {},
                "statuses": [
                    {"created_at": st.created_at.isoformat(), "status": "pending"}
                ],
            },
            auth=auth,
        ) as resp:
            await resp.json()

        bake_uri = _mk_bake_uri(self._fs, st.attempt.bake)
        attempt_url = bake_uri / f"{st.attempt.number:02d}.attempt"

        data = {
            "id": _id_to_json(st.id),
            "raw_id": st.raw_id or "",
            "when": st.when.isoformat(),
            "created_at": st.created_at.isoformat(),
        }
        await self._write_json(attempt_url / f"{data['id']}.started.json", data)

    async def write_finish(self, ft: FinishedTask) -> None:
        attempt_data = await self._find_attempt_data(ft.attempt.bake, ft.attempt.number)
        auth = await self._config._api_auth()

        try:
            async with self._core.request(
                "GET",
                self._base_url / "api/v1/flow/tasks/by_yaml_id",
                params={
                    "attempt_id": attempt_data["id"],
                    "yaml_id": _id_to_json(ft.id),
                },
                auth=auth,
            ) as resp:
                payload = await resp.json()
                statuses = payload["statuses"]
        except ResourceNotFound:
            statuses = []

        statuses.append(
            {"created_at": ft.created_at.isoformat(), "status": ft.status.value}
        )

        task_data = {
            "yaml_id": _id_to_json(ft.id),
            "attempt_id": attempt_data["id"],
            "raw_id": ft.raw_id or "",
            "outputs": ft.outputs,
            "state": ft.state,
            "statuses": statuses,
        }

        if len(statuses) == 1:
            # create new task record
            async with self._core.request(
                "POST",
                self._base_url / "api/v1/flow/tasks",
                json=task_data,
                auth=auth,
            ) as resp:
                await resp.json()
        else:
            # update existing task
            async with self._core.request(
                "PUT",
                self._base_url / "api/v1/flow/tasks/replace",
                json=task_data,
                auth=auth,
            ) as resp:
                await resp.json()

        bake_uri = _mk_bake_uri(self._fs, ft.attempt.bake)
        attempt_url = bake_uri / f"{ft.attempt.number:02d}.attempt"
        data = {
            "id": _id_to_json(ft.id),
            "raw_id": ft.raw_id or "",
            "when": ft.when.isoformat(),
            "status": ft.status.value,
            "exit_code": None,
            "created_at": ft.created_at.isoformat(),
            "started_at": ft.started_at.isoformat(),
            "finished_at": ft.finished_at.isoformat(),
            "finish_reason": "",
            "finish_description": "",
            "outputs": ft.outputs,
            "state": ft.state,
        }
        await self._write_json(attempt_url / f"{data['id']}.finished.json", data)

    async def check_cache(
        self,
        attempt: Attempt,
        task_id: FullID,
        caching_key: str,
        life_span: datetime.timedelta,
    ) -> Optional[FinishedTask]:
        prj = await self._get_project(attempt.bake.project)

        auth = await self._config._api_auth()
        try:
            async with self._core.request(
                "GET",
                self._base_url / "api/v1/flow/cache_entries/by_key",
                params={
                    "project_id": prj.id,
                    "task_id": _id_to_json(task_id),
                    "batch": attempt.bake.batch,
                    "key": caching_key,
                },
                auth=auth,
            ) as resp:
                payload = await resp.json()
        except ResourceNotFound:
            return None

        created_at = datetime.datetime.fromisoformat(payload["created_at"])
        now = datetime.datetime.now(datetime.timezone.utc)
        eol = created_at + life_span
        if eol < now:
            return None
        if payload["key"] != caching_key:
            return None

        st = StartedTask(
            attempt=attempt,
            id=task_id,
            raw_id="",
            when=created_at,
            created_at=created_at,
        )
        await self.write_start(st)
        ft = FinishedTask(
            attempt=attempt,
            id=task_id,
            raw_id="",
            when=created_at,
            status=TaskStatus.CACHED,
            created_at=created_at,
            started_at=created_at,
            finished_at=created_at,
            outputs=payload["outputs"],
            state=payload["state"],
        )
        await self.write_finish(ft)
        return ft

    async def write_cache(
        self,
        attempt: Attempt,
        ft: FinishedTask,
        caching_key: str,
    ) -> None:
        prj = await self._get_project(attempt.bake.project)

        auth = await self._config._api_auth()
        async with self._core.request(
            "POST",
            self._base_url / "api/v1/flow/cache_entries",
            json={
                "project_id": prj.id,
                "task_id": _id_to_json(ft.id),
                "batch": attempt.bake.batch,
                "key": caching_key,
                "outputs": ft.outputs,
                "state": ft.state,
            },
            auth=auth,
        ) as resp:
            await resp.json()

        url = _mk_cache_uri(self._fs, attempt, ft.id)
        assert ft.raw_id is not None, (ft.id, ft.raw_id)

        data = {
            "when": ft.when.isoformat(),
            "caching_key": caching_key,
            "raw_id": ft.raw_id or "",
            "status": ft.status.value,
            "exit_code": None,
            "created_at": ft.created_at.isoformat(),
            "started_at": ft.started_at.isoformat(),
            "finished_at": ft.finished_at.isoformat(),
            "finish_reason": "",
            "finish_description": "",
            "outputs": ft.outputs,
            "state": ft.state,
        }
        try:
            await self._write_json(url, data, overwrite=True)
        except ResourceNotFound:
            await self._fs.mkdir(url.parent, parents=True)
            await self._write_json(url, data, overwrite=True)

    async def clear_cache(self, project: str, batch: Optional[str] = None) -> None:
        prj = await self._get_project(project)

        auth = await self._config._api_auth()
        async with self._core.request(
            "DELETE",
            self._base_url / "api/v1/flow/cache_entries",
            params={
                "project_id": prj.id,
                "batch": batch,
            },
            auth=auth,
        ) as resp:
            await resp.json()

        await self._fs.rm(_mk_cache_uri2(self._fs, project, batch), recursive=True)

    async def _write_file(
        self, url: URL, body: str, *, overwrite: bool = False
    ) -> None:
        await self._fs.create(url, body.encode("utf-8"))

    async def _write_config(self, bake_id: str, filename: str, body: str) -> str:
        url = self._base_url / "api/v1/flow/config_files"
        auth = await self._config._api_auth()
        async with self._core.request(
            "POST",
            url,
            json={
                "bake_id": bake_id,
                "filename": filename,
                "content": body,
            },
            auth=auth,
        ) as resp:
            data = await resp.json()
            return str(data["id"])

    async def _write_json(
        self, url: URL, data: Dict[str, Any], *, overwrite: bool = False
    ) -> None:
        if not data.get("when"):
            data["when"] = _now().isoformat()

        await self._write_file(url, json.dumps(data), overwrite=overwrite)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _dt2str(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _live_to_json(live: Live) -> Dict[str, Any]:
    return {
        "project": live.project,
        "when": live.when.isoformat(),
        "jobs": [
            {"id": job.id, "multi": job.multi, "tags": job.tags} for job in live.jobs
        ],
    }


def _mk_bake_uri_from_id(
    fs: FileSystem, project: str, batch: str, when: datetime.datetime, suffix: str
) -> URL:
    bake_id = "_".join([batch, _dt2str(when), suffix])
    return fs.root / project / bake_id


def _mk_bake_uri(fs: FileSystem, bake: Bake) -> URL:
    return _mk_bake_uri_from_id(fs, bake.project, bake.batch, bake.when, bake.suffix)


def _bake_to_json(bake: Bake) -> Dict[str, Any]:
    graphs = {}
    for pre, gr in bake.graphs.items():
        graphs[_id_to_json(pre)] = {
            _id_to_json(full_id): [_id_to_json(dep) for dep in deps]
            for full_id, deps in gr.items()
        }
    return {
        "project": bake.project,
        "batch": bake.batch,
        "when": bake.when.isoformat(),
        "suffix": bake.suffix,
        "graphs": graphs,
        "params": bake.params,
        "name": bake.name,
        "tags": bake.tags,
    }


def _bake_from_json(data: Dict[str, Any]) -> Bake:
    graphs = {}
    for pre, gr in data["graphs"].items():
        graphs[_id_from_json(pre)] = {
            _id_from_json(full_id): {_id_from_json(dep) for dep in deps}
            for full_id, deps in gr.items()
        }
    return Bake(
        project=data["project"],
        batch=data["batch"],
        when=datetime.datetime.fromisoformat(data["when"]),
        suffix=data["suffix"],
        graphs=graphs,
        params=data["params"],
        name=data.get("name"),
        tags=data.get("tags", []),
    )


def _bake_from_api_json(project: Project, data: Dict[str, Any]) -> Bake:
    graphs = {}
    for pre, gr in data["graphs"].items():
        graphs[_id_from_json(pre)] = {
            _id_from_json(full_id): {_id_from_json(dep) for dep in deps}
            for full_id, deps in gr.items()
        }
    digest = hashlib.new("sha256")
    digest.update(project.name.encode("utf8"))
    digest.update(data["batch"].encode("utf8"))
    #    digest.update(json.dumps(data["graphs"], sort_keys=True).encode("utf8"))
    digest.update(json.dumps(data["params"], sort_keys=True).encode("utf8"))
    assert data["project_id"] == project.id
    return Bake(
        project=project.name,
        batch=data["batch"],
        when=datetime.datetime.fromisoformat(data["created_at"]),
        suffix=digest.hexdigest()[:6],
        graphs=graphs,
        params=data["params"],
        name=data["name"],
        tags=data["tags"],
    )


def _id_to_json(full_id: FullID) -> str:
    return ".".join(full_id)


def _id_from_json(sid: str) -> FullID:
    if not sid:
        return ()
    else:
        return tuple(sid.split("."))


def _attempt_to_json(attempt: Attempt) -> Dict[str, Any]:
    return {
        "number": attempt.number,
        "bake": _bake_to_json(attempt.bake),
        "when": attempt.when.isoformat(),
    }


def _attempt_from_json(
    init_data: Dict[str, Any], result_data: Optional[Dict[str, Any]]
) -> Attempt:
    if result_data is not None:
        result = TaskStatus(result_data["result"])
    else:
        result = TaskStatus.RUNNING
    return Attempt(
        bake=_bake_from_json(init_data["bake"]),
        when=datetime.datetime.fromisoformat(init_data["when"]),
        number=init_data["number"],
        result=result,
        executor_id=None,
    )


def _attempt_from_api_json(bake: Bake, data: Dict[str, Any]) -> Attempt:
    return Attempt(
        bake=bake,
        when=datetime.datetime.fromisoformat(data["created_at"]),
        number=data["number"],
        result=TaskStatus(data["result"]),
        executor_id=data.get("executor_id"),
    )


def _mk_cache_uri(fs: FileSystem, attempt: Attempt, task_id: FullID) -> URL:
    return _mk_cache_uri2(fs, attempt.bake.project, attempt.bake.batch) / (
        _id_to_json(task_id) + ".json"
    )


def _mk_cache_uri2(fs: FileSystem, project: str, batch: Optional[str]) -> URL:
    ret = fs.root / project / ".cache"
    if batch:
        ret /= batch
    return ret


class _RawStatusItem(TypedDict):
    created_at: str
    status: str


class _StatusItem(TypedDict):
    created_at: datetime.datetime
    status: TaskStatus


def _parse_statuses(statuses: List[_RawStatusItem]) -> List[_StatusItem]:
    return [
        {
            "created_at": datetime.datetime.fromisoformat(item["created_at"]),
            "status": TaskStatus(item["status"]),
        }
        for item in statuses
    ]


def _find_started_at(statuses: List[_StatusItem]) -> datetime.datetime:
    for item in reversed(statuses):
        if item["status"] == TaskStatus.PENDING:
            return item["created_at"]
    else:
        raise ValueError("Task is not started")


def _find_finished_at(statuses: List[_StatusItem]) -> datetime.datetime:
    for item in reversed(statuses):
        if item["status"] in (
            TaskStatus.CACHED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.SUCCEEDED,
        ):
            return item["created_at"]
    else:
        raise ValueError("Task is not finished")
