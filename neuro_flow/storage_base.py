from dataclasses import dataclass

import abc
import datetime
from typing import (
    AbstractSet,
    AsyncIterator,
    Mapping,
    Optional,
    Sequence,
    Type,
    Union,
    overload,
)

from neuro_flow.types import FullID, ImageStatus, TaskStatus


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    owner: str
    cluster: str


@dataclass(frozen=True)
class LiveJob:
    id: str
    yaml_id: str
    project_id: str
    multi: bool
    tags: Sequence[str]
    raw_id: Optional[str] = None


@dataclass(frozen=True)
class Bake:
    id: str
    project_id: str
    batch: str
    name: Optional[str]
    tags: Sequence[str]
    created_at: datetime.datetime
    # prefix -> { id -> deps }
    graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]]
    params: Optional[Mapping[str, str]]
    last_attempt: Optional["Attempt"]


@dataclass(frozen=True)
class ConfigsMeta:
    workspace: str
    flow_config_id: str
    project_config_id: Optional[str]
    action_config_ids: Mapping[str, str]


@dataclass(frozen=True)
class Attempt:
    id: str
    bake_id: str
    number: int
    created_at: datetime.datetime
    result: TaskStatus
    configs_meta: ConfigsMeta
    executor_id: Optional[str] = None


@dataclass(frozen=True)
class TaskStatusItem:
    when: datetime.datetime
    status: TaskStatus


@dataclass(frozen=True)
class Task:
    id: str
    yaml_id: FullID
    attempt_id: str
    raw_id: Optional[str]
    outputs: Optional[Mapping[str, str]]
    state: Optional[Mapping[str, str]]
    statuses: Sequence[TaskStatusItem]


@dataclass(frozen=True)
class ConfigFile:
    id: str
    bake_id: str
    filename: str
    content: str


@dataclass(frozen=True)
class CacheEntry:
    id: str
    project_id: str
    task_id: FullID
    batch: str
    key: str
    created_at: datetime.datetime
    outputs: Mapping[str, str]
    state: Mapping[str, str]
    raw_id: str = ""


@dataclass(frozen=True)
class BakeImage:
    id: str
    bake_id: str
    yaml_defs: Sequence[FullID]
    ref: str
    status: ImageStatus
    context_on_storage: Optional[str] = None
    dockerfile_rel: Optional[str] = None
    builder_job_id: Optional[str] = None


class _Unset:
    pass


class Storage(abc.ABC):
    @overload
    def project(self, *, id: str) -> "ProjectStorage":
        pass

    @overload
    def project(self, *, name: str, cluster: Optional[str] = None) -> "ProjectStorage":
        pass

    @abc.abstractmethod
    def project(
        self,
        *,
        id: Optional[str] = None,
        name: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> "ProjectStorage":
        pass

    @abc.abstractmethod
    async def create_project(self, name: str, cluster: Optional[str] = None) -> Project:
        pass

    @abc.abstractmethod
    def list_projects(
        self, name: str, cluster: Optional[str] = None
    ) -> AsyncIterator[Project]:
        pass


class ProjectStorage(abc.ABC):
    @abc.abstractmethod
    async def get(self) -> Project:
        pass

    @abc.abstractmethod
    async def delete(self) -> None:
        pass

    @abc.abstractmethod
    def list_bakes(
        self,
        tags: Optional[AbstractSet[str]] = None,
        since: Optional[datetime.datetime] = None,
        until: Optional[datetime.datetime] = None,
        recent_first: bool = False,
    ) -> AsyncIterator[Bake]:
        pass

    @abc.abstractmethod
    async def create_bake(
        self,
        batch: str,
        # prefix -> { id -> deps }
        graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]],
        params: Optional[Mapping[str, str]] = None,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
    ) -> Bake:
        pass

    @overload
    def bake(self, *, id: str) -> "BakeStorage":
        pass

    @overload
    def bake(self, *, name: str) -> "BakeStorage":
        pass

    @abc.abstractmethod
    def bake(
        self,
        *,
        id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> "BakeStorage":
        pass

    @abc.abstractmethod
    async def create_cache_entry(
        self,
        task_id: FullID,
        batch: str,
        key: str,
        outputs: Mapping[str, str],
        state: Mapping[str, str],
        raw_id: str,
    ) -> CacheEntry:
        pass

    @abc.abstractmethod
    async def delete_cache_entries(
        self,
        batch: Optional[str] = None,
        task_id: Optional[FullID] = None,
    ) -> None:
        pass

    @overload
    def cache_entry(self, *, id: str) -> "CacheEntryStorage":
        pass

    @overload
    def cache_entry(
        self, *, task_id: FullID, batch: str, key: str
    ) -> "CacheEntryStorage":
        pass

    @abc.abstractmethod
    def cache_entry(
        self,
        *,
        id: Optional[str] = None,
        task_id: Optional[FullID] = None,
        batch: Optional[str] = None,
        key: Optional[str] = None,
    ) -> "CacheEntryStorage":
        pass

    @abc.abstractmethod
    def list_live_jobs(
        self,
    ) -> AsyncIterator[LiveJob]:
        pass

    @abc.abstractmethod
    async def create_live_job(
        self,
        yaml_id: str,
        multi: bool,
        tags: Sequence[str],
        raw_id: Optional[str] = None,
    ) -> LiveJob:
        pass

    @abc.abstractmethod
    async def replace_live_job(
        self,
        yaml_id: str,
        multi: bool,
        tags: Sequence[str],
        raw_id: Optional[str] = None,
    ) -> LiveJob:
        pass

    @overload
    def live_job(self, *, id: str) -> "LiveJobStorage":
        pass

    @overload
    def live_job(
        self,
        *,
        yaml_id: str,
    ) -> "LiveJobStorage":
        pass

    @abc.abstractmethod
    def live_job(
        self,
        *,
        id: Optional[str] = None,
        yaml_id: Optional[str] = None,
    ) -> "LiveJobStorage":
        pass


class BakeStorage(abc.ABC):
    @abc.abstractmethod
    async def get(self) -> Bake:
        pass

    @abc.abstractmethod
    def list_attempts(self) -> AsyncIterator[Attempt]:
        pass

    @abc.abstractmethod
    async def create_attempt(
        self,
        configs_meta: ConfigsMeta,
        number: Optional[int] = None,
        executor_id: Optional[str] = None,
        result: TaskStatus = TaskStatus.PENDING,
    ) -> Attempt:
        pass

    @abc.abstractmethod
    async def create_config_file(
        self,
        filename: str,
        content: str,
    ) -> ConfigFile:
        pass

    @abc.abstractmethod
    def list_bake_images(self) -> AsyncIterator[BakeImage]:
        pass

    @abc.abstractmethod
    async def create_bake_images(
        self,
        yaml_defs: Sequence[FullID],
        ref: str,
        status: ImageStatus = ImageStatus.PENDING,
        context_on_storage: Optional[str] = None,
        dockerfile_rel: Optional[str] = None,
        builder_job_id: Optional[str] = None,
    ) -> BakeImage:
        pass

    @overload
    def attempt(self, *, id: str) -> "AttemptStorage":
        pass

    @overload
    def attempt(self, *, number: int) -> "AttemptStorage":
        pass

    @abc.abstractmethod
    def attempt(
        self,
        *,
        id: Optional[str] = None,
        number: Optional[int] = None,
    ) -> "AttemptStorage":
        pass

    @abc.abstractmethod
    def config_file(
        self,
        *,
        id: str,
    ) -> "ConfigFileStorage":
        pass

    @abc.abstractmethod
    def bake_image(
        self,
        *,
        id: str,
    ) -> "BakeImageStorage":
        pass


class AttemptStorage(abc.ABC):
    @abc.abstractmethod
    async def get(self) -> Attempt:
        pass

    @abc.abstractmethod
    async def update(
        self,
        *,
        executor_id: Union[Optional[str], Type[_Unset]] = _Unset,
        result: Union[TaskStatus, Type[_Unset]] = _Unset,
    ) -> Attempt:
        pass

    @abc.abstractmethod
    def list_tasks(self) -> AsyncIterator[Task]:
        pass

    @abc.abstractmethod
    async def create_task(
        self,
        yaml_id: FullID,
        raw_id: Optional[str],
        status: TaskStatusItem,
        outputs: Optional[Mapping[str, str]] = None,
        state: Optional[Mapping[str, str]] = None,
    ) -> Task:
        pass

    @overload
    def task(self, *, id: str) -> "TaskStorage":
        pass

    @overload
    def task(self, *, yaml_id: FullID) -> "TaskStorage":
        pass

    @abc.abstractmethod
    def task(
        self,
        *,
        id: Optional[str] = None,
        yaml_id: Optional[FullID] = None,
    ) -> "TaskStorage":
        pass


class TaskStorage(abc.ABC):
    @abc.abstractmethod
    async def get(self) -> Task:
        pass

    @abc.abstractmethod
    async def update(
        self,
        *,
        outputs: Union[Optional[Mapping[str, str]], Type[_Unset]] = _Unset,
        state: Union[Optional[Mapping[str, str]], Type[_Unset]] = _Unset,
        new_status: Optional[TaskStatusItem] = None,
    ) -> Task:
        pass


class ConfigFileStorage(abc.ABC):
    @abc.abstractmethod
    async def get(self) -> ConfigFile:
        pass


class CacheEntryStorage(abc.ABC):
    @abc.abstractmethod
    async def get(self) -> CacheEntry:
        pass


class BakeImageStorage(abc.ABC):
    @abc.abstractmethod
    async def get(self) -> BakeImage:
        pass

    @abc.abstractmethod
    async def update(
        self,
        *,
        status: Union[ImageStatus, Type[_Unset]] = _Unset,
        builder_job_id: Union[Optional[str], Type[_Unset]] = _Unset,
    ) -> BakeImage:
        pass


class LiveJobStorage(abc.ABC):
    @abc.abstractmethod
    async def get(self) -> LiveJob:
        pass
