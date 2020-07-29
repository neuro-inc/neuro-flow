import dataclasses

import abc
import datetime
import json
import secrets
import sys
from neuromation.api import Client, JobStatus, get as api_get
from types import TracebackType
from typing import Any, Dict, Optional, Set, Tuple, Type
from yarl import URL


if sys.version_info < (3, 7):
    from backports.datetime_fromisoformat import MonkeyPatch

    MonkeyPatch.patch_fromisoformat()


@dataclasses.dataclass(frozen=True)
class BakeInit:
    id: str
    config_file: URL
    cardinality: int
    when: datetime.datetime


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
    exit_code: int
    created_at: datetime.datetime
    started_at: datetime.datetime
    finished_at: datetime.datetime
    finish_reason: str
    finish_description: str


# A storage abstraction
#
# There is a possibility to add Postgres storage class later, for example


class BatchStorage(abc.ABC):
    @abc.abstractmethod
    async def create_bake(self, batch_name: str, config_content: str) -> str:
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

    def now(self) -> str:
        dt = datetime.datetime.now(datetime.timezone.utc)
        return dt.isoformat(timespec="seconds")

    def _mk_bake_uri(self, bake_id: str) -> URL:
        return URL("storage:.flow") / bake_id

    async def create_bake(
        self, batch_name: str, config_name: str, config_content: str, cardinality: int
    ) -> str:
        # Return bake_id
        bake_id = "_".join([batch_name, self.now(), secrets.token_hex(3)])
        bake_uri = self._mk_bake_uri(bake_id)
        await self._client.storage.mkdir(bake_uri, parents=True)
        config_uri = bake_uri / config_name
        await self._write_file(config_uri, config_content)
        started = {
            "config_file": str(config_uri),
            "id": batch_name,
            "cardinality": cardinality,
        }
        await self._write_json(bake_uri / "00.init.json", started)
        return bake_id

    async def fetch_bake_init(self, bake_id: str) -> BakeInit:
        data = self._fetch_json(self._mk_bake_uri() / "00.init.json")
        assert data["id"] == bake_id
        return BakeInit(
            bake_id=data["id"],
            config_file=URL(data["config_file"]),
            cardinality=URL(data["cardinality"]),
            when=datetime.fromisoformat(data["when"]),
        )

    async def create_attempt(
        self, bake_id: str, attempt_no: int, cardinality: int
    ) -> str:
        assert 1 < attempt_no < 100
        bake_uri = self._mk_bake_uri(bake_id)
        attempt_uri = bake_uri / f"{attempt_no:2d}.attempt"
        await self._client.storage.mkdir(attempt_uri)
        digits = cardinality // 10 + 1
        pre = "0".zfill(digits)
        await self._write_json(f"{pre}.init.json", {"cardinality": cardinality})

    async def find_last_attempt(self, bake_id: str) -> int:
        bake_uri = self._mk_bake_uri(bake_id)
        files = set()
        for chunk in self._client.storage.ls(bake_uri):
            for i in chunk:
                files.add(i.name)
        if "00.init.json" not in files:
            raise ValueError("The batch is not initialized properly")
        for attempt_no in range(99, 0, -1):
            if f"{attempt_no:2d}.attempt" in files:
                return attempt_no
        assert False, "unreachable"

    async def fetch_attempt(
        self, bake_id: str, attempt_no: int, cardinality: int
    ) -> Tuple[Set[FinishedTask], Set[StartedTask]]:
        bake_uri = self._mk_bake_uri(bake_id)
        attempt_url = bake_uri / f"{attempt_no:2d}attempt"
        digits = cardinality // 10 + 1
        pre = "0".zfill(digits)
        data = await self._read_json(attempt_url / f"{pre.init.json}")
        assert data["cardinality"] == cardinality

    async def _read_file(self, url: URL) -> str:
        ret = []
        async for chunk in self._client.storage.open(url):
            ret.append(chunk)
        return b"".join(ret).decode("utf-8")

    async def _read_json(self, url: URL) -> Dict[str, Any]:
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
        for chunk in self._client.storage.ls(url.parent):
            for i in chunk:
                files.add(i.name)
        if url.name in files:
            raise ValueError(f"File {url} already exists")
        await self._client.storage.create(url, body.encode("utf-8"))

    async def _write_json(self, url: URL, data: Dict[str, Any]) -> None:
        data["when"] = self.now()

        await self._write_file(url, json.dumps(data))
