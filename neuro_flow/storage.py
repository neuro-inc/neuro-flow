import dataclasses

import abc
import datetime
import json
import re
import secrets
import sys
from neuromation.api import Client, JobDescription, JobStatus
from types import TracebackType
from typing import Any, AsyncIterator, Dict, Mapping, Optional, Tuple, Type
from typing_extensions import Final
from yarl import URL

from .context import Result
from .parser import ConfigDir


if sys.version_info < (3, 7):
    from backports.datetime_fromisoformat import MonkeyPatch

    MonkeyPatch.patch_fromisoformat()


STARTED_RE: Final = re.compile(r"\A\d+\.(?P<id>[a-zA-Z][a-zA-Z0-9_\-]*).started.json\Z")
FINISHED_RE: Final = re.compile(
    r"\A\d+\.(?P<id>[a-zA-Z][a-zA-Z0-9_\-]*).finished.json\Z"
)


@dataclasses.dataclass(frozen=True)
class BakeId:
    project: str
    batch: str
    when: datetime.datetime
    suffix: str

    def __str__(self) -> str:
        folder = "_".join([self.batch, _dt2str(self.when), self.suffix])
        return f"{self.project} {folder}"


@dataclasses.dataclass(frozen=True)
class BakeInit:
    project: str
    batch: str
    when: datetime.datetime
    suffix: str
    config_name: str
    cardinality: int

    @property
    def bake_id(self) -> BakeId:
        return BakeId(
            project=self.project, batch=self.batch, when=self.when, suffix=self.suffix
        )


@dataclasses.dataclass(frozen=True)
class StartedTask:
    id: str
    raw_id: str
    created_at: datetime.datetime
    when: datetime.datetime


@dataclasses.dataclass(frozen=True)
class FinishedTask:
    id: str
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

    @property
    def result(self) -> Result:
        if self.status == JobStatus.SUCCEEDED:
            return Result.SUCCEEDED
        else:
            return Result.FAILED


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
    async def list_bakes(self) -> AsyncIterator[BakeInit]:
        pass

    @abc.abstractmethod
    async def create_bake(
        self, batch: str, config_name: str, config_content: str, cardinality: int,
    ) -> BakeInit:
        pass

    @abc.abstractmethod
    async def fetch_bake(self, bake: BakeId) -> BakeInit:
        pass

    @abc.abstractmethod
    async def fetch_config(self, bake: BakeId, config_name: str) -> str:
        pass

    @abc.abstractmethod
    async def create_attempt(
        self, bake: BakeId, attempt_no: int, cardinality: int
    ) -> None:
        pass

    @abc.abstractmethod
    async def find_last_attempt(self, bake: BakeId) -> int:
        pass

    @abc.abstractmethod
    async def fetch_attempt(
        self, bake: BakeId, attempt_no: int, cardinality: int
    ) -> Tuple[Dict[str, FinishedTask], Dict[str, StartedTask]]:
        pass

    @abc.abstractmethod
    async def finish_attempt(
        self, bake: BakeId, attempt_no: int, cardinality: int, result: Result
    ) -> None:
        pass

    @abc.abstractmethod
    async def start_task(
        self,
        bake: BakeId,
        attempt_no: int,
        task_no: int,
        cardinality: int,
        task_id: str,
        descr: JobDescription,
    ) -> StartedTask:
        pass

    @abc.abstractmethod
    async def finish_task(
        self,
        bake: BakeId,
        attempt_no: int,
        task_no: int,
        cardinality: int,
        task: StartedTask,
        descr: JobDescription,
        outputs: Mapping[str, str],
    ) -> FinishedTask:
        pass


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
    #     +-- config.yml
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

    def __init__(self, client: Client, config_dir: ConfigDir) -> None:
        self._client = client
        self._config_dir = config_dir

    async def close(self) -> None:
        pass

    async def list_bakes(self) -> AsyncIterator[BakeInit]:
        pass

    async def create_bake(
        self, batch: str, config_name: str, config_content: str, cardinality: int,
    ) -> BakeInit:
        when = _now()
        bake = BakeId(
            project=self._config_dir.workspace.name,
            batch=batch,
            when=when,
            suffix=secrets.token_hex(3),
        )
        bake_uri = _mk_bake_uri(bake)
        await self._client.storage.mkdir(bake_uri, parents=True)
        config_uri = bake_uri / config_name
        await self._write_file(config_uri, config_content)

        ret = BakeInit(
            project=bake.project,
            batch=bake.batch,
            when=bake.when,
            suffix=bake.suffix,
            config_name=config_name,
            cardinality=cardinality,
        )

        data = {
            "project": ret.project,
            "batch": ret.batch,
            "when": _dt2str(ret.when),
            "suffix": ret.suffix,
            "config_file": ret.config_name,
            "cardinality": ret.cardinality,
        }
        await self._write_json(bake_uri / "00.init.json", data)
        return ret

    async def fetch_bake(self, bake: BakeId) -> BakeInit:
        data = await self._read_json(_mk_bake_uri(bake) / "00.init.json")
        return BakeInit(
            project=data["project"],
            batch=data["batch"],
            when=datetime.datetime.fromisoformat(data["when"]),
            suffix=data["suffix"],
            config_name=data["config_file"],
            cardinality=data["cardinality"],
        )

    async def fetch_config(self, bake: BakeId, config_name: str) -> str:
        return await self._read_file(_mk_bake_uri(bake) / config_name)

    async def create_attempt(
        self, bake: BakeId, attempt_no: int, cardinality: int
    ) -> None:
        assert 0 < attempt_no < 100, attempt_no
        bake_uri = _mk_bake_uri(bake)
        attempt_uri = bake_uri / f"{attempt_no:02d}.attempt"
        await self._client.storage.mkdir(attempt_uri)
        digits = cardinality // 10 + 1
        pre = "0".zfill(digits)
        await self._write_json(
            attempt_uri / f"{pre}.init.json", {"cardinality": cardinality}
        )

    async def find_last_attempt(self, bake: BakeId) -> int:
        bake_uri = _mk_bake_uri(bake)
        files = set()
        async for fi in self._client.storage.ls(bake_uri):
            files.add(fi.name)
        if "00.init.json" not in files:
            raise ValueError("The batch is not initialized properly")
        for attempt_no in range(99, 0, -1):
            if f"{attempt_no:02d}.attempt" in files:
                return attempt_no
        assert False, "unreachable"

    async def fetch_attempt(
        self, bake: BakeId, attempt_no: int, cardinality: int
    ) -> Tuple[Dict[str, FinishedTask], Dict[str, StartedTask]]:
        bake_uri = _mk_bake_uri(bake)
        attempt_url = bake_uri / f"{attempt_no:02d}.attempt"
        digits = cardinality // 10 + 1
        pre = "0".zfill(digits)
        init_name = f"{pre}.init.json"
        data = await self._read_json(attempt_url / init_name)
        assert data["cardinality"] == cardinality
        started = {}
        finished = {}
        async for fs in self._client.storage.ls(attempt_url):
            if fs.name == init_name:
                continue
            match = STARTED_RE.match(fs.name)
            if match:
                data = await self._read_json(attempt_url / fs.name)
                assert match.group("id") == data["id"]
                started[data["id"]] = StartedTask(
                    data["id"],
                    data["raw_id"],
                    datetime.datetime.fromisoformat(data["created_at"]),
                    datetime.datetime.fromisoformat(data["when"]),
                )
                continue
            match = FINISHED_RE.match(fs.name)
            if match:
                data = await self._read_json(attempt_url / fs.name)
                assert match.group("id") == data["id"]
                finished[data["id"]] = FinishedTask(
                    data["id"],
                    data["raw_id"],
                    datetime.datetime.fromisoformat(data["when"]),
                    JobStatus(data["status"]),
                    data["exit_code"],
                    datetime.datetime.fromisoformat(data["created_at"]),
                    datetime.datetime.fromisoformat(data["started_at"]),
                    datetime.datetime.fromisoformat(data["finished_at"]),
                    finish_reason=data["finish_reason"],
                    finish_description=data["finish_description"],
                    outputs=data["outputs"],
                )
                continue
            raise ValueError(f"Unexpected name {attempt_url / fs.name}")
        assert finished.keys() <= started.keys()
        return finished, started

    async def finish_attempt(
        self, bake: BakeId, attempt_no: int, cardinality: int, result: Result
    ) -> None:
        bake_uri = _mk_bake_uri(bake)
        attempt_url = bake_uri / f"{attempt_no:02d}.attempt"
        digits = cardinality // 10 + 1
        pre = "9" * digits
        data = {"result": str(result)}
        await self._write_json(attempt_url / f"{pre}.result.json", data)

    async def start_task(
        self,
        bake: BakeId,
        attempt_no: int,
        task_no: int,
        cardinality: int,
        task_id: str,
        descr: JobDescription,
    ) -> StartedTask:
        bake_uri = _mk_bake_uri(bake)
        attempt_url = bake_uri / f"{attempt_no:02d}.attempt"
        digits = cardinality // 10 + 1
        pre = str(task_no + 1).zfill(digits)
        assert descr.history.created_at is not None
        ret = StartedTask(
            id=task_id,
            raw_id=descr.id,
            when=datetime.datetime.now(datetime.timezone.utc),
            created_at=descr.history.created_at,
        )

        data = {
            "id": ret.id,
            "raw_id": ret.raw_id,
            "when": ret.when.isoformat(timespec="seconds"),
            "created_at": ret.created_at.isoformat(timespec="seconds"),
        }
        await self._write_json(attempt_url / f"{pre}.{ret.id}.started.json", data)
        return ret

    async def finish_task(
        self,
        bake: BakeId,
        attempt_no: int,
        task_no: int,
        cardinality: int,
        task: StartedTask,
        descr: JobDescription,
        outputs: Mapping[str, str],
    ) -> FinishedTask:
        assert task.raw_id == descr.id
        assert task.created_at == descr.history.created_at
        bake_uri = _mk_bake_uri(bake)
        attempt_url = bake_uri / f"{attempt_no:02d}.attempt"
        digits = cardinality // 10 + 1
        pre = str(task_no + 1).zfill(digits)
        assert descr.history.created_at is not None
        assert descr.history.started_at is not None
        assert descr.history.finished_at is not None
        ret = FinishedTask(
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

        data = {
            "id": ret.id,
            "raw_id": ret.raw_id,
            "when": ret.when.isoformat(timespec="seconds"),
            "status": str(ret.status),
            "exit_code": ret.exit_code,
            "created_at": ret.created_at.isoformat(timespec="seconds"),
            "started_at": ret.started_at.isoformat(timespec="seconds"),
            "finished_at": ret.finished_at.isoformat(timespec="seconds"),
            "finish_reason": ret.finish_reason,
            "finish_description": ret.finish_description,
            "outputs": ret.outputs,
        }
        await self._write_json(attempt_url / f"{pre}.{task.id}.finished.json", data)
        return ret

    async def _read_file(self, url: URL) -> str:
        ret = []
        async for chunk in self._client.storage.open(url):
            ret.append(chunk)
        return b"".join(ret).decode("utf-8")

    async def _read_json(self, url: URL) -> Any:
        data = await self._read_file(url)
        return json.loads(data)

    async def _write_file(self, url: URL, body: str) -> None:
        # TODO: Prevent overriding the target on the storage.
        #
        # It might require platform_storage_api change.
        #
        # There is no clean understanding if the storage can support this strong
        # guarantee at all.
        files = set()
        async for fi in self._client.storage.ls(url.parent):
            files.add(fi.name)
        if url.name in files:
            raise ValueError(f"File {url} already exists")
        await self._client.storage.create(url, body.encode("utf-8"))

    async def _write_json(self, url: URL, data: Dict[str, Any]) -> None:
        if not data.get("when"):
            data["when"] = _dt2str(_now())

        await self._write_file(url, json.dumps(data))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _dt2str(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _mk_bake_uri(bake: BakeId) -> URL:
    folder = "_".join([bake.batch, _dt2str(bake.when), bake.suffix])
    return URL("storage:.flow") / bake.project / folder
