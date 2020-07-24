import abc
import datetime
import json
import secrets
from neuromation.api import Client, get as api_get
from types import TracebackType
from typing import Any, Dict, Optional, Type
from yarl import URL


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
    #     +-- 00.root.json
    #     +-- 01.attempt-<N>
    #         +-- 000.begin.json
    #         +-- 001.<task_id>.started.json
    #         +-- 002.<task_id>.finished.json
    #         +-- 999.result.json
    #     +-- 99.result.json

    def __init__(self) -> None:
        self._client: Optional[Client] = None

    async def __aenter__(self) -> "BatchFSStorage":
        self._client = await api_get()
        return self

    async def __aexit__(
        self,
        exc_typ: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._client is not None:
            await self._client.close()

    async def create_bake(self, batch_name: str, config_content: str) -> str:
        # Return bake_id
        assert self._client is not None
        now = datetime.datetime.now(datetime.timezone.utc)
        bake_id = "_".join(
            [batch_name, now.isoformat(timespec="seconds"), secrets.token_hex(3)]
        )
        bake_uri = URL("storage:.flow") / bake_id
        await self._client.storage.mkdir(bake_uri, parents=True)
        await self._write_file(bake_uri / "config.yml", config_content)
        started = {
            "config_file": "config.yml",
            "id": batch_name,
        }
        await self._write_json(bake_uri / "00.root.json", started)
        return bake_id

    async def create_attempt(self, batch_name: str, attempt_no: int) -> str:
        pass

    async def find_last_attempt(self, batch_name: str) -> int:
        pass

    async def _write_file(self, url: URL, body: str) -> None:
        # TODO: Prevent overriding the target on the storage.
        #
        # It might require platform_storage_api change.
        #
        # There is no clean understanding if the storage can support this strong
        # guarantee at all.
        assert self._client is not None
        await self._client.storage.create(url, body.encode("utf-8"))

    async def _write_json(self, url: URL, data: Dict[str, Any]) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        data["when"] = now.isoformat(timespec="seconds"),

        await self._write_file(url, json.dumps(data))
