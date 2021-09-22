from dataclasses import replace

import aiohttp
import datetime
import json
import sys
from neuro_sdk import Client
from typing import (
    AbstractSet,
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)
from yarl import URL

from neuro_flow.storage.base import (
    Attempt,
    AttemptStorage,
    Bake,
    BakeImage,
    BakeImageStorage,
    BakeStorage,
    CacheEntry,
    CacheEntryStorage,
    ConfigFile,
    ConfigFileStorage,
    ConfigsMeta,
    LiveJob,
    LiveJobStorage,
    Project,
    ProjectStorage,
    Storage,
    Task,
    TaskStatusItem,
    TaskStorage,
    _Unset,
)
from neuro_flow.types import FullID, ImageStatus, TaskStatus
from neuro_flow.utils import retry


if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


def _id_from_json(sid: str) -> FullID:
    if not sid:
        return ()
    else:
        return tuple(sid.split("."))


def _id_to_json(full_id: FullID) -> str:
    return ".".join(full_id)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _dt2str(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse_project_payload(data: Mapping[str, Any]) -> Project:
    return Project(
        id=data["id"],
        yaml_id=data["name"],
        owner=data["owner"],
        cluster=data["cluster"],
    )


def _parse_live_job_payload(data: Mapping[str, Any]) -> LiveJob:
    return LiveJob(
        id=data["id"],
        yaml_id=data["yaml_id"],
        project_id=data["project_id"],
        multi=data["multe"],
        tags=data["tags"],
        raw_id=data.get("raw_id", None),
    )


def _parse_cache_entry_payload(data: Mapping[str, Any]) -> CacheEntry:
    return CacheEntry(
        id=data["id"],
        project_id=data["project_id"],
        batch=data["batch"],
        task_id=_id_from_json(data["task_id"]),
        key=data["key"],
        created_at=datetime.datetime.fromisoformat(data["created_at"]),
        outputs=data["outputs"],
        state=data["state"],
        raw_id=data.get("raw_id", None),
    )


def _parse_task_payload(data: Mapping[str, Any]) -> Task:
    return Task(
        id=data["id"],
        yaml_id=_id_from_json(data["yaml_id"]),
        attempt_id=data["attempt_id"],
        outputs=data["outputs"],
        state=data["state"],
        raw_id=data.get("raw_id", None),
        statuses=[
            TaskStatusItem(
                when=datetime.datetime.fromisoformat(item["created_at"]),
                status=TaskStatus(item["status"]),
            )
            for item in data["statuses"]
        ],
    )


def _parse_config_file_payload(data: Mapping[str, Any]) -> ConfigFile:
    return ConfigFile(
        id=data["id"],
        bake_id=data["bake_id"],
        filename=data["filename"],
        content=data["content"],
    )


def _parse_bake_payload(data: Mapping[str, Any]) -> Bake:
    graphs = {}
    for pre, gr in data["graphs"].items():
        graphs[_id_from_json(pre)] = {
            _id_from_json(full_id): {_id_from_json(dep) for dep in deps}
            for full_id, deps in gr.items()
        }
    last_attempt: Optional[Attempt] = data.get("last_attempt")
    if last_attempt:
        last_attempt = _parse_attempt_payload(data["last_attempt"])

    return Bake(
        id=data["id"],
        project_id=data["project_id"],
        name=data["name"],
        batch=data["batch"],
        tags=data["tags"],
        created_at=datetime.datetime.fromisoformat(data["created_at"]),
        graphs=graphs,
        params=data["params"],
        last_attempt=last_attempt,
    )


def _parse_attempt_payload(data: Mapping[str, Any]) -> Attempt:
    return Attempt(
        id=data.get("id", "FIX THIS"),
        bake_id=data["bake_id"],
        number=data["number"],
        created_at=datetime.datetime.fromisoformat(data["created_at"]),
        result=TaskStatus(data["result"]),
        configs_meta=ConfigsMeta(
            workspace=data["configs_meta"]["workspace"],
            flow_config_id=data["configs_meta"]["flow_config_id"],
            project_config_id=data["configs_meta"]["project_config_id"],
            action_config_ids=data["configs_meta"]["action_config_ids"],
        ),
        executor_id=data.get("executor_id", None),
    )


def _parse_bake_image_payload(data: Mapping[str, Any]) -> BakeImage:
    context_on_storage_raw = data.get("context_on_storage", None)
    context_on_storage: Optional[URL] = None
    if context_on_storage_raw is not None:
        context_on_storage = URL(context_on_storage_raw)
    return BakeImage(
        id=data["id"],
        bake_id=data["bake_id"],
        yaml_defs=[_id_from_json(sid) for sid in data["yaml_defs"]],
        ref=data["ref"],
        status=ImageStatus(data["status"]),
        context_on_storage=context_on_storage,
        dockerfile_rel=data.get("dockerfile_rel", None),
        builder_job_id=data.get("builder_job_id", None),
    )


class RawApiClient:
    def __init__(self, client: Client) -> None:
        self._core = client._core
        self._config = client.config
        self._base_url = client.config.api_url

    E = TypeVar("E")

    @asynccontextmanager
    async def _request(
        self,
        method: str,
        url_suffix: str,
        data: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        params: Union[Sequence[Tuple[str, str]], Mapping[str, str], None] = None,
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        url = self._base_url / url_suffix
        auth = await self._config._api_auth()
        async with self._core.request(
            method,
            url,
            headers=headers,
            auth=auth,
            json=data,
            params=params,
        ) as resp:
            yield resp

    async def list(
        self,
        url_suffix: str,
        mapper: Callable[[Mapping[str, Any]], E],
        params: Union[Sequence[Tuple[str, str]], Mapping[str, str], None] = None,
    ) -> AsyncIterator[E]:
        headers = {"Accept": "application/x-ndjson"}
        async with self._request(
            "GET", url_suffix, headers=headers, params=params
        ) as resp:
            async for line in resp.content:
                yield mapper(json.loads(line))

    async def create(
        self,
        url_suffix: str,
        data: Mapping[str, Any],
        mapper: Callable[[Mapping[str, Any]], E],
    ) -> E:
        async with self._request("POST", url_suffix, data=data) as resp:
            return mapper(await resp.json())

    async def update(
        self,
        url_suffix: str,
        data: Mapping[str, Any],
        mapper: Callable[[Mapping[str, Any]], E],
    ) -> E:
        async with self._request("PUT", url_suffix, data=data) as resp:
            return mapper(await resp.json())

    async def patch(
        self,
        url_suffix: str,
        data: Mapping[str, Any],
        mapper: Callable[[Mapping[str, Any]], E],
    ) -> E:
        async with self._request("PATCH", url_suffix, data=data) as resp:
            return mapper(await resp.json())

    async def get(
        self,
        url_suffix: str,
        mapper: Callable[[Mapping[str, Any]], E],
        params: Union[Sequence[Tuple[str, str]], Mapping[str, str], None] = None,
    ) -> E:
        async with self._request("GET", url_suffix, params=params) as resp:
            return mapper(await resp.json())

    async def delete(
        self,
        url_suffix: str,
        params: Union[Sequence[Tuple[str, str]], Mapping[str, str], None] = None,
    ) -> None:
        async with self._request("DELETE", url_suffix, params=params):
            pass


class RetryingReadRawApiClient(RawApiClient):
    def __init__(self, client: Client) -> None:
        super().__init__(client)

    E = TypeVar("E")

    @retry
    async def get(
        self,
        url_suffix: str,
        mapper: Callable[[Mapping[str, Any]], E],
        params: Union[Sequence[Tuple[str, str]], Mapping[str, str], None] = None,
    ) -> E:
        return await super().get(url_suffix, mapper, params)

    @retry
    async def _list(
        self,
        url_suffix: str,
        mapper: Callable[[Mapping[str, Any]], E],
        params: Union[Sequence[Tuple[str, str]], Mapping[str, str], None] = None,
    ) -> List[E]:
        res = []
        async for item in super().list(url_suffix, mapper, params):
            res.append(item)
        return res

    async def list(
        self,
        url_suffix: str,
        mapper: Callable[[Mapping[str, Any]], E],
        params: Union[Sequence[Tuple[str, str]], Mapping[str, str], None] = None,
    ) -> AsyncIterator[E]:
        for item in await self._list(url_suffix, mapper, params):
            yield item


class ApiStorage(Storage):
    def __init__(
        self, client: Client, _raw_client: Optional[RawApiClient] = None
    ) -> None:
        self._client = client
        self._cluster_name = client.config.cluster_name
        self._raw_client = RawApiClient(client)

    def with_retry_read(self) -> Storage:
        return ApiStorage(
            self._client, _raw_client=RetryingReadRawApiClient(self._client)
        )

    async def close(self) -> None:
        pass

    def project(
        self,
        *,
        id: Optional[str] = None,
        yaml_id: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> "ProjectStorage":
        cluster = cluster or self._cluster_name

        async def id_getter() -> Tuple[str, Optional[Project]]:
            if id:
                return id, None
            else:
                assert yaml_id
                assert cluster
                project = await self._raw_client.get(
                    "flow/projects/by_name",
                    _parse_project_payload,
                    params={
                        "name": yaml_id,
                        "cluster": cluster,
                    },
                )
                return project.id, project

        return ApiProjectStorage(self._raw_client, id_getter)

    async def create_project(
        self, yaml_id: str, cluster: Optional[str] = None
    ) -> Project:
        return await self._raw_client.create(
            "flow/projects",
            data={"name": yaml_id, "cluster": cluster},
            mapper=_parse_project_payload,
        )

    def list_projects(
        self, name: str, cluster: Optional[str] = None
    ) -> AsyncIterator[Project]:
        return self._raw_client.list("flow/projects", _parse_project_payload)

    def bake(self, *, id: str) -> "BakeStorage":
        async def id_getter() -> Tuple[str, Optional[Bake]]:
            return id, None

        return ApiBakeStorage(self._raw_client, id_getter)


E = TypeVar("E")


class DeferredIdMixin(Generic[E]):
    _id_getter: Callable[[], Awaitable[Tuple[str, Optional[E]]]]
    _id: Optional[str] = None

    async def _get_id(self) -> Tuple[str, Optional[E]]:
        if self._id:
            return self._id, None
        id_, entity = await self._id_getter()  # type: ignore
        self._id = id_
        return id_, entity


class ApiProjectStorage(DeferredIdMixin[Project], ProjectStorage):
    def __init__(
        self,
        raw_client: RawApiClient,
        id_getter: Callable[[], Awaitable[Tuple[str, Optional[Project]]]],
    ):
        self._raw_client = raw_client
        self._id_getter = id_getter  # type: ignore

    async def get(self) -> Project:
        project_id, project = await self._get_id()
        if project:
            return project
        return await self._raw_client.get(
            f"flow/projects/{project_id}", _parse_project_payload
        )

    async def delete(self) -> None:
        project_id, _ = await self._get_id()
        await self._raw_client.delete(f"flow/projects/{project_id}")

    async def list_bakes(
        self,
        tags: Optional[AbstractSet[str]] = None,
        since: Optional[datetime.datetime] = None,
        until: Optional[datetime.datetime] = None,
        recent_first: bool = False,
    ) -> AsyncIterator[Bake]:
        project_id, _ = await self._get_id()

        params = [("project_id", project_id), ("fetch_last_attempt", "1")]
        if tags is not None:
            params += [("tags", tag) for tag in tags]
        if since is not None:
            params += [("since", since.isoformat())]
        if until is not None:
            params += [("until", until.isoformat())]
        if recent_first:
            params += [("reverse", "true")]

        async for bake in self._raw_client.list(
            f"flow/bakes", _parse_bake_payload, params=params
        ):
            yield bake

    async def create_bake(
        self,
        batch: str,
        graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]],
        params: Optional[Mapping[str, str]] = None,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
    ) -> Bake:
        project_id, _ = await self._get_id()
        graph = {}
        for k1, v1 in graphs.items():
            subgraph = {}
            for k2, v2 in v1.items():
                subgraph[_id_to_json(k2)] = [_id_to_json(it) for it in v2]
            graph[_id_to_json(k1)] = subgraph

        bake_payload = {
            "project_id": project_id,
            "batch": batch,
            "graphs": graph,
            "params": params,
            "name": name,
            "tags": tags,
        }
        return await self._raw_client.create(
            "flow/bakes", bake_payload, _parse_bake_payload
        )

    async def create_cache_entry(
        self,
        task_id: FullID,
        batch: str,
        key: str,
        outputs: Mapping[str, str],
        state: Mapping[str, str],
        raw_id: str,
    ) -> CacheEntry:
        project_id, _ = await self._get_id()
        cache_entry_payload = {
            "project_id": project_id,
            "batch": batch,
            "task_id": _id_to_json(task_id),
            "key": key,
            "outputs": outputs,
            "state": state,
            "raw_id": raw_id,
        }
        return await self._raw_client.create(
            "flow/cache_entries", cache_entry_payload, _parse_cache_entry_payload
        )

    async def delete_cache_entries(
        self,
        batch: Optional[str] = None,
        task_id: Optional[FullID] = None,
    ) -> None:
        project_id, _ = await self._get_id()
        params = [("project_id", project_id)]
        if batch is not None:
            params += [("batch", batch)]
        if task_id is not None:
            params += [("task_id", _id_to_json(task_id))]
        await self._raw_client.delete("flow/cache_entries", params)

    async def list_live_jobs(self) -> AsyncIterator[LiveJob]:
        project_id, _ = await self._get_id()

        async for live_job in self._raw_client.list(
            f"flow/live_jobs",
            _parse_live_job_payload,
            params={"project_id": project_id},
        ):
            yield live_job

    async def create_live_job(
        self,
        yaml_id: str,
        multi: bool,
        tags: Iterable[str],
        raw_id: Optional[str] = None,
    ) -> LiveJob:
        project_id, _ = await self._get_id()
        payload = {
            "project_id": project_id,
            "yaml_id": yaml_id,
            "tags": list(tags),
            "raw_id": raw_id,
            "multi": multi,
        }
        return await self._raw_client.create(
            "flow/live_jobs", payload, _parse_live_job_payload
        )

    async def replace_live_job(
        self,
        yaml_id: str,
        multi: bool,
        tags: Iterable[str],
        raw_id: Optional[str] = None,
    ) -> LiveJob:
        project_id, _ = await self._get_id()
        payload = {
            "project_id": project_id,
            "yaml_id": yaml_id,
            "tags": list(tags),
            "raw_id": raw_id,
            "multi": multi,
        }
        return await self._raw_client.update(
            "flow/live_jobs/replace", payload, _parse_live_job_payload
        )

    def live_job(
        self, *, id: Optional[str] = None, yaml_id: Optional[str] = None
    ) -> "LiveJobStorage":
        async def id_getter() -> Tuple[str, Optional[LiveJob]]:
            if id:
                return id, None
            else:
                project_id, _ = await self._get_id()
                assert yaml_id
                live_job = await self._raw_client.get(
                    "flow/live_jobs/by_yaml_id",
                    _parse_live_job_payload,
                    params={
                        "project_id": project_id,
                        "yaml_id": yaml_id,
                    },
                )
                return live_job.id, live_job

        return ApiLiveJobStorage(self._raw_client, id_getter)

    def bake(
        self, *, id: Optional[str] = None, name: Optional[str] = None
    ) -> "BakeStorage":
        async def id_getter() -> Tuple[str, Optional[Bake]]:
            if id:
                return id, None
            else:
                project_id, _ = await self._get_id()
                assert name
                project = await self._raw_client.get(
                    "flow/bakes/by_name",
                    _parse_bake_payload,
                    params={
                        "name": name,
                        "project_id": project_id,
                        "fetch_last_attempt": "1",
                    },
                )
                return project.id, project

        return ApiBakeStorage(self._raw_client, id_getter)

    def cache_entry(
        self,
        *,
        id: Optional[str] = None,
        task_id: Optional[FullID] = None,
        batch: Optional[str] = None,
        key: Optional[str] = None,
    ) -> "CacheEntryStorage":
        async def id_getter() -> Tuple[str, Optional[CacheEntry]]:
            if id:
                return id, None
            else:
                project_id, _ = await self._get_id()
                assert batch
                assert key
                assert task_id
                cache_entry = await self._raw_client.get(
                    "flow/cache_entries/by_key",
                    _parse_cache_entry_payload,
                    params={
                        "project_id": project_id,
                        "batch": batch,
                        "task_id": _id_to_json(task_id),
                        "key": key,
                    },
                )
                return cache_entry.id, cache_entry

        return ApiCacheEntryStorage(self._raw_client, id_getter)


class ApiBakeStorage(DeferredIdMixin[Bake], BakeStorage):
    def __init__(
        self,
        raw_client: RawApiClient,
        id_getter: Callable[[], Awaitable[Tuple[str, Optional[Bake]]]],
    ):
        self._raw_client = raw_client
        self._id_getter = id_getter  # type: ignore

    async def get(self) -> Bake:
        bake_id, bake = await self._get_id()
        if bake:
            return bake
        return await self._raw_client.get(
            f"flow/bakes/{bake_id}",
            _parse_bake_payload,
            params={"fetch_last_attempt": "1"},
        )

    async def list_attempts(self) -> AsyncIterator[Attempt]:
        bake_id, _ = await self._get_id()

        async for attempt in self._raw_client.list(
            f"flow/attempts", _parse_attempt_payload, params={"bake_id": bake_id}
        ):
            yield attempt

    async def create_attempt(
        self,
        configs_meta: ConfigsMeta,
        number: Optional[int] = None,
        executor_id: Optional[str] = None,
        result: TaskStatus = TaskStatus.PENDING,
    ) -> Attempt:
        bake_id, _ = await self._get_id()
        payload = {
            "bake_id": bake_id,
            "number": number,
            "executor_id": executor_id,
            "result": result.value,
            "configs_meta": {
                "workspace": configs_meta.workspace,
                "flow_config_id": configs_meta.flow_config_id,
                "project_config_id": configs_meta.project_config_id,
                "action_config_ids": configs_meta.action_config_ids,
            },
        }
        return await self._raw_client.create(
            f"flow/attempts", payload, _parse_attempt_payload
        )

    async def create_config_file(self, filename: str, content: str) -> ConfigFile:
        bake_id, _ = await self._get_id()
        payload = {
            "bake_id": bake_id,
            "filename": filename,
            "content": content,
        }
        return await self._raw_client.create(
            f"flow/config_files", payload, _parse_config_file_payload
        )

    async def list_bake_images(self) -> AsyncIterator[BakeImage]:
        bake_id, _ = await self._get_id()

        async for attempt in self._raw_client.list(
            f"flow/bake_images", _parse_bake_image_payload, params={"bake_id": bake_id}
        ):
            yield attempt

    async def create_bake_image(
        self,
        yaml_defs: Sequence[FullID],
        ref: str,
        status: ImageStatus = ImageStatus.PENDING,
        context_on_storage: Optional[URL] = None,
        dockerfile_rel: Optional[str] = None,
        builder_job_id: Optional[str] = None,
    ) -> BakeImage:
        bake_id, _ = await self._get_id()
        payload = {
            "bake_id": bake_id,
            "yaml_defs": [_id_to_json(yaml_id) for yaml_id in yaml_defs],
            "ref": ref,
            "status": status.value,
            "context_on_storage": str(context_on_storage)
            if context_on_storage
            else None,
            "dockerfile_rel": dockerfile_rel,
            "builder_job_id": builder_job_id,
        }
        return await self._raw_client.create(
            f"flow/bake_images", payload, _parse_bake_image_payload
        )

    def attempt(
        self, *, id: Optional[str] = None, number: Optional[int] = None
    ) -> "AttemptStorage":
        async def id_getter() -> Tuple[str, Optional[Attempt]]:
            if id:
                return id, None
            else:
                bake_id, _ = await self._get_id()
                attempt = await self._raw_client.get(
                    "flow/attempts/by_number",
                    _parse_attempt_payload,
                    params={
                        "bake_id": bake_id,
                        "number": str(number),
                    },
                )
                return attempt.id, attempt

        return ApiAttemptStorage(self._raw_client, id_getter)

    def config_file(self, *, id: str) -> "ConfigFileStorage":
        async def id_getter() -> Tuple[str, Optional[ConfigFile]]:
            return id, None

        return ApiConfigFileStorage(self._raw_client, id_getter)

    def bake_image(
        self, *, id: Optional[str] = None, ref: Optional[str] = None
    ) -> "BakeImageStorage":
        async def id_getter() -> Tuple[str, Optional[BakeImage]]:
            if id:
                return id, None
            else:
                assert ref
                bake_id, _ = await self._get_id()
                bake_image = await self._raw_client.get(
                    "flow/live_jobs/by_ref",
                    _parse_bake_image_payload,
                    params={
                        "bake_id": bake_id,
                        "ref": ref,
                    },
                )
                return bake_image.id, bake_image

        return ApiBakeImageStorage(self._raw_client, id_getter)


class ApiCacheEntryStorage(DeferredIdMixin[CacheEntry], CacheEntryStorage):
    def __init__(
        self,
        raw_client: RawApiClient,
        id_getter: Callable[[], Awaitable[Tuple[str, Optional[CacheEntry]]]],
    ):
        self._raw_client = raw_client
        self._id_getter = id_getter  # type: ignore

    async def get(self) -> CacheEntry:
        entry_id, entry = await self._get_id()
        if entry:
            return entry
        return await self._raw_client.get(
            f"flow/cache_entries/{entry_id}", _parse_cache_entry_payload
        )


class ApiLiveJobStorage(DeferredIdMixin[LiveJob], LiveJobStorage):
    def __init__(
        self,
        raw_client: RawApiClient,
        id_getter: Callable[[], Awaitable[Tuple[str, Optional[LiveJob]]]],
    ):
        self._raw_client = raw_client
        self._id_getter = id_getter  # type: ignore

    async def get(self) -> LiveJob:
        live_job_id, live_job = await self._get_id()
        if live_job:
            return live_job
        return await self._raw_client.get(
            f"flow/live_jobs/{live_job_id}", _parse_live_job_payload
        )


class ApiAttemptStorage(DeferredIdMixin[Attempt], AttemptStorage):
    def __init__(
        self,
        raw_client: RawApiClient,
        id_getter: Callable[[], Awaitable[Tuple[str, Optional[Attempt]]]],
    ):
        self._raw_client = raw_client
        self._id_getter = id_getter  # type: ignore

    async def get(self) -> Attempt:
        attempt_id, attempt = await self._get_id()
        if attempt:
            return attempt
        return await self._raw_client.get(
            f"flow/attempts/{attempt_id}", _parse_attempt_payload
        )

    async def update(
        self,
        *,
        executor_id: Union[Optional[str], Type[_Unset]] = _Unset,
        result: Union[TaskStatus, Type[_Unset]] = _Unset,
    ) -> Attempt:
        # TODO: Use PATCH when implemented on server
        attempt = await self.get()
        if executor_id is not _Unset:
            attempt = replace(attempt, executor_id=executor_id)
        if result is not _Unset:
            attempt = replace(attempt, result=result)
        payload = {
            "bake_id": attempt.bake_id,
            "number": attempt.number,
            "executor_id": attempt.executor_id,
            "result": attempt.result.value,
            "configs_meta": {
                "workspace": attempt.configs_meta.workspace,
                "flow_config_id": attempt.configs_meta.flow_config_id,
                "project_config_id": attempt.configs_meta.project_config_id,
                "action_config_ids": attempt.configs_meta.action_config_ids,
            },
        }
        return await self._raw_client.update(
            "flow/attempts/replace", data=payload, mapper=_parse_attempt_payload
        )

    async def list_tasks(self) -> AsyncIterator[Task]:
        attempt_id, _ = await self._get_id()

        async for task in self._raw_client.list(
            f"flow/tasks", _parse_task_payload, params={"attempt_id": attempt_id}
        ):
            yield task

    async def create_task(
        self,
        yaml_id: FullID,
        raw_id: Optional[str],
        status: Union[TaskStatusItem, TaskStatus],
        outputs: Optional[Mapping[str, str]] = None,
        state: Optional[Mapping[str, str]] = None,
    ) -> Task:
        if isinstance(status, TaskStatus):
            status = TaskStatusItem(when=_now(), status=status)
        attempt_id, _ = await self._get_id()
        task_payload = {
            "attempt_id": attempt_id,
            "yaml_id": _id_to_json(yaml_id),
            "raw_id": raw_id,
            "outputs": outputs,
            "state": state,
            "statuses": [
                {
                    "created_at": _dt2str(status.when),
                    "status": status.status.value,
                }
            ],
        }
        return await self._raw_client.create(
            "flow/tasks", task_payload, _parse_task_payload
        )

    def task(
        self, *, id: Optional[str] = None, yaml_id: Optional[FullID] = None
    ) -> "TaskStorage":
        async def id_getter() -> Tuple[str, Optional[Task]]:
            if id:
                return id, None

            else:

                assert yaml_id
                attempt_id, _ = await self._get_id()

                task = await self._raw_client.get(
                    "flow/tasks/by_yaml_id",
                    _parse_task_payload,
                    params={
                        "attempt_id": attempt_id,
                        "yaml_id": ".".join(yaml_id),
                    },
                )
                return task.id, task

        return ApiTaskStorage(self._raw_client, id_getter)


class ApiConfigFileStorage(DeferredIdMixin[ConfigFile], ConfigFileStorage):
    def __init__(
        self,
        raw_client: RawApiClient,
        id_getter: Callable[[], Awaitable[Tuple[str, Optional[ConfigFile]]]],
    ):
        self._raw_client = raw_client
        self._id_getter = id_getter  # type: ignore

    async def get(self) -> ConfigFile:
        config_file_id, config_file = await self._get_id()
        if config_file:
            return config_file
        return await self._raw_client.get(
            f"flow/config_files/{config_file_id}", _parse_config_file_payload
        )


class ApiBakeImageStorage(DeferredIdMixin[BakeImage], BakeImageStorage):
    def __init__(
        self,
        raw_client: RawApiClient,
        id_getter: Callable[[], Awaitable[Tuple[str, Optional[BakeImage]]]],
    ):
        self._raw_client = raw_client
        self._id_getter = id_getter  # type: ignore

    async def get(self) -> BakeImage:
        bake_image_id, bake_image = await self._get_id()
        if bake_image:
            return bake_image
        return await self._raw_client.get(
            f"flow/bake_images/{bake_image_id}", _parse_bake_image_payload
        )

    async def update(
        self,
        *,
        status: Union[ImageStatus, Type[_Unset]] = _Unset,
        builder_job_id: Union[Optional[str], Type[_Unset]] = _Unset,
    ) -> BakeImage:
        bake_image_id, _ = await self._get_id()

        patch_data: Dict[str, Any] = {}
        if status != _Unset:
            patch_data["status"] = status
        if builder_job_id != _Unset:
            patch_data["builder_job_id"] = builder_job_id
        return await self._raw_client.patch(
            f"flow/bake_images/{bake_image_id}", patch_data, _parse_bake_image_payload
        )


class ApiTaskStorage(DeferredIdMixin[Task], TaskStorage):
    def __init__(
        self,
        raw_client: RawApiClient,
        id_getter: Callable[[], Awaitable[Tuple[str, Optional[Task]]]],
    ):
        self._raw_client = raw_client
        self._id_getter = id_getter  # type: ignore

    async def get(self) -> Task:
        task_id, task = await self._get_id()
        if task:
            return task
        return await self._raw_client.get(f"flow/tasks/{task_id}", _parse_task_payload)

    async def update(
        self,
        *,
        outputs: Union[Optional[Mapping[str, str]], Type[_Unset]] = _Unset,
        state: Union[Optional[Mapping[str, str]], Type[_Unset]] = _Unset,
        new_status: Optional[Union[TaskStatusItem, TaskStatus]] = None,
    ) -> Task:
        # TODO: Use PATCH when implemented on server
        task = await self.get()
        if outputs is not _Unset:
            task = replace(task, outputs=outputs)
        if state is not _Unset:
            task = replace(task, state=state)
        if new_status:
            if isinstance(new_status, TaskStatus):
                new_status = TaskStatusItem(when=_now(), status=new_status)
            task = replace(task, statuses=[*task.statuses, new_status])
        task_payload = {
            "attempt_id": task.attempt_id,
            "yaml_id": _id_to_json(task.yaml_id),
            "raw_id": task.raw_id,
            "outputs": task.outputs,
            "state": task.state,
            "statuses": [
                {
                    "created_at": _dt2str(item.when),
                    "status": item.status.value,
                }
                for item in task.statuses
            ],
        }
        return await self._raw_client.update(
            f"flow/tasks/replace", task_payload, _parse_task_payload
        )
