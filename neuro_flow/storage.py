import dataclasses

import abc
import datetime
import json
import logging
import re
import secrets
import sys
from neuromation.api import Client, JobDescription, JobStatus
from types import TracebackType
from typing import AbstractSet, Any, AsyncIterator, Dict, Mapping, Optional, Tuple, Type
from typing_extensions import Final
from yarl import URL


if sys.version_info < (3, 7):
    from backports.datetime_fromisoformat import MonkeyPatch

    MonkeyPatch.patch_fromisoformat()


log = logging.getLogger(__name__)

STARTED_RE: Final = re.compile(r"\A\d+\.(?P<id>[a-zA-Z][a-zA-Z0-9_\-]*).started.json\Z")
FINISHED_RE: Final = re.compile(
    r"\A\d+\.(?P<id>[a-zA-Z][a-zA-Z0-9_\-]*).finished.json\Z"
)


@dataclasses.dataclass(frozen=True)
class Bake:
    project: str
    batch: str
    when: datetime.datetime
    suffix: str
    config_name: str
    cardinality: int
    graph: Mapping[str, AbstractSet[str]]

    def __str__(self) -> str:
        folder = "_".join([self.batch, _dt2str(self.when), self.suffix])
        return f"{self.project} {folder}"

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
    id: str
    raw_id: str
    created_at: datetime.datetime
    when: datetime.datetime


@dataclasses.dataclass(frozen=True)
class FinishedTask:
    attempt: Attempt
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
        bake = Bake(
            project="project",
            batch="batch",
            when=datetime.datetime.now(),
            suffix="suffix",
            config_name="config_name",
            cardinality=1,
            graph={},
        )
        yield bake

    @abc.abstractmethod
    async def create_bake(
        self,
        project: str,
        batch: str,
        config_name: str,
        config_content: str,
        cardinality: int,
        graph: Mapping[str, AbstractSet[str]],
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
    async def fetch_config(self, bake: Bake) -> str:
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
    ) -> Tuple[Dict[str, StartedTask], Dict[str, FinishedTask]]:
        pass

    @abc.abstractmethod
    async def finish_attempt(self, attempt: Attempt, result: JobStatus) -> None:
        pass

    @abc.abstractmethod
    async def start_task(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: str,
        descr: JobDescription,
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

    def __init__(self, client: Client) -> None:
        self._client = client

    async def close(self) -> None:
        pass

    async def list_bakes(self, project: str) -> AsyncIterator[Bake]:
        url = URL(f"storage:.flow") / project
        try:
            fs = await self._client.storage.stat(url)
            if not fs.is_dir():
                raise ValueError(f"{url} is not a directory")
        except ValueError:
            raise ValueError(f"Cannot find remote project {url}")

        async for fs in self._client.storage.ls(url):
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
        config_name: str,
        config_content: str,
        cardinality: int,
        graph: Mapping[str, AbstractSet[str]],
    ) -> Bake:
        when = _now()
        bake = Bake(
            project=project,
            batch=batch,
            when=when,
            suffix=secrets.token_hex(3),
            config_name=config_name,
            cardinality=cardinality,
            graph=graph,
        )
        bake_uri = _mk_bake_uri(bake)
        await self._client.storage.mkdir(bake_uri, parents=True)
        config_uri = bake_uri / config_name
        await self._write_file(config_uri, config_content)

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
            _mk_bake_uri_from_id(project, batch, when, suffix) / "00.init.json"
        )
        return _bake_from_json(data)

    async def fetch_bake_by_id(self, project: str, bake_id: str) -> Bake:
        url = URL(f"storage:.flow") / project / bake_id
        data = await self._read_json(url / "00.init.json")
        return _bake_from_json(data)

    async def fetch_config(self, bake: Bake) -> str:
        return await self._read_file(_mk_bake_uri(bake) / bake.config_name)

    async def create_attempt(self, bake: Bake, attempt_no: int) -> Attempt:
        assert 0 < attempt_no < 100, attempt_no
        bake_uri = _mk_bake_uri(bake)
        attempt_uri = bake_uri / f"{attempt_no:02d}.attempt"
        await self._client.storage.mkdir(attempt_uri)
        digits = bake.cardinality // 10 + 1
        pre = "0".zfill(digits)
        when = _now()
        ret = Attempt(bake=bake, when=when, number=attempt_no, result=JobStatus.PENDING)
        await self._write_json(attempt_uri / f"{pre}.init.json", _attempt_to_json(ret))
        return ret

    async def find_attempt(self, bake: Bake, attempt_no: int = -1) -> Attempt:
        bake_uri = _mk_bake_uri(bake)
        if attempt_no == -1:
            files = set()
            async for fi in self._client.storage.ls(bake_uri):
                files.add(fi.name)
            for attempt_no in range(99, 0, -1):
                fname = f"{attempt_no:02d}.attempt"
                if fname in files:
                    return await self.find_attempt(bake, attempt_no)
            assert False, "unreachable"
        else:
            assert 0 < attempt_no < 99
            fname = f"{attempt_no:02d}.attempt"
            digits = bake.cardinality // 10 + 1
            pre = "0".zfill(digits)
            init_name = f"{pre}.init.json"
            init_data = await self._read_json(bake_uri / fname / init_name)
            pre = "9" * digits
            result_name = f"{pre}.result.json"
            try:
                result_data = await self._read_json(bake_uri / fname / result_name)
            except ValueError:
                result_data = None
            return _attempt_from_json(init_data, result_data)

    async def fetch_attempt(
        self, attempt: Attempt
    ) -> Tuple[Dict[str, StartedTask], Dict[str, FinishedTask]]:
        bake_uri = _mk_bake_uri(attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        digits = attempt.bake.cardinality // 10 + 1
        pre = "0".zfill(digits)
        init_name = f"{pre}.init.json"
        pre = "9" * digits
        result_name = f"{pre}.result.json"
        data = await self._read_json(attempt_url / init_name)
        started = {}
        finished = {}
        async for fs in self._client.storage.ls(attempt_url):
            if fs.name == init_name:
                continue
            if fs.name == result_name:
                continue
            match = STARTED_RE.match(fs.name)
            if match:
                data = await self._read_json(attempt_url / fs.name)
                assert match.group("id") == data["id"]
                started[data["id"]] = StartedTask(
                    attempt=attempt,
                    id=data["id"],
                    raw_id=data["raw_id"],
                    created_at=datetime.datetime.fromisoformat(data["created_at"]),
                    when=datetime.datetime.fromisoformat(data["when"]),
                )
                continue
            match = FINISHED_RE.match(fs.name)
            if match:
                data = await self._read_json(attempt_url / fs.name)
                assert match.group("id") == data["id"]
                finished[data["id"]] = FinishedTask(
                    attempt=attempt,
                    id=data["id"],
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
            raise ValueError(f"Unexpected name {attempt_url / fs.name}")
        assert finished.keys() <= started.keys()
        return started, finished

    async def finish_attempt(self, attempt: Attempt, result: JobStatus) -> None:
        bake_uri = _mk_bake_uri(attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        digits = attempt.bake.cardinality // 10 + 1
        pre = "9" * digits
        data = {"result": result.value}
        await self._write_json(attempt_url / f"{pre}.result.json", data)

    async def start_task(
        self,
        attempt: Attempt,
        task_no: int,
        task_id: str,
        descr: JobDescription,
    ) -> StartedTask:
        bake_uri = _mk_bake_uri(attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        digits = attempt.bake.cardinality // 10 + 1
        pre = str(task_no + 1).zfill(digits)
        assert descr.history.created_at is not None
        ret = StartedTask(
            attempt=attempt,
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
        attempt: Attempt,
        task_no: int,
        task: StartedTask,
        descr: JobDescription,
        outputs: Mapping[str, str],
    ) -> FinishedTask:
        assert task.raw_id == descr.id
        assert task.created_at == descr.history.created_at
        bake_uri = _mk_bake_uri(attempt.bake)
        attempt_url = bake_uri / f"{attempt.number:02d}.attempt"
        digits = attempt.bake.cardinality // 10 + 1
        pre = str(task_no + 1).zfill(digits)
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

        data = {
            "id": ret.id,
            "raw_id": ret.raw_id,
            "when": ret.when.isoformat(timespec="seconds"),
            "status": ret.status.value,
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


def _mk_bake_uri_from_id(
    project: str, batch: str, when: datetime.datetime, suffix: str
) -> URL:
    bake_id = "_".join([batch, _dt2str(when), suffix])
    return URL("storage:.flow") / project / bake_id


def _mk_bake_uri(bake: Bake) -> URL:
    return _mk_bake_uri_from_id(bake.project, bake.batch, bake.when, bake.suffix)


def _bake_to_json(bake: Bake) -> Dict[str, Any]:
    return {
        "project": bake.project,
        "batch": bake.batch,
        "when": _dt2str(bake.when),
        "suffix": bake.suffix,
        "config_name": bake.config_name,
        "cardinality": bake.cardinality,
        "graph": [[k, sorted(v)] for k, v in bake.graph.items()],
    }


def _bake_from_json(data: Dict[str, Any]) -> Bake:
    return Bake(
        project=data["project"],
        batch=data["batch"],
        when=datetime.datetime.fromisoformat(data["when"]),
        suffix=data["suffix"],
        config_name=data["config_name"],
        cardinality=data["cardinality"],
        graph={i[0]: set(i[1]) for i in data["graph"]},
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
