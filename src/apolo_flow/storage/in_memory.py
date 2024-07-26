from dataclasses import replace

import datetime
import secrets
from apolo_sdk import ResourceNotFound
from typing import (
    AbstractSet,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Type,
    Union,
)
from yarl import URL

from apolo_flow.storage.base import (
    Attempt,
    AttemptStorage,
    Bake,
    BakeImage,
    BakeImageStorage,
    BakeMeta,
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
from apolo_flow.types import FullID, ImageStatus, TaskStatus


def _make_id() -> str:
    return secrets.token_hex(10)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class InMemoryDB:
    def __init__(self) -> None:
        self.projects: Dict[str, Project] = {}
        self.bakes: Dict[str, Bake] = {}
        self.cache_entries: Dict[str, CacheEntry] = {}
        self.live_jobs: Dict[str, LiveJob] = {}
        self.attempts: Dict[str, Attempt] = {}
        self.config_files: Dict[str, ConfigFile] = {}
        self.bake_images: Dict[str, BakeImage] = {}
        self.tasks: Dict[str, Task] = {}


class InMemoryStorage(Storage):
    def __init__(
        self,
        owner: str = "in_memory_owner",
        cluster: str = "in_memory_cluster",
        org_name: str = "in_memory_org",
        project_name: str = "in_memory_project",
    ):
        self._owner = owner
        self._cluster = cluster
        self._org_name = org_name
        self._project_name = project_name
        self._db = InMemoryDB()

    def with_retry_read(self) -> "Storage":
        return self  # In memory read cannot fail

    async def close(self) -> None:
        pass

    def project(
        self,
        *,
        id: Optional[str] = None,
        project_name: Optional[str] = None,
        yaml_id: Optional[str] = None,
        cluster: Optional[str] = None,
        org_name: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> "ProjectStorage":
        if id:
            return InMemoryProjectStorage(id, self._db)
        cluster = cluster or self._cluster
        org_name = org_name or self._org_name
        project_name = project_name or self._project_name
        for project in self._db.projects.values():
            if (
                project.yaml_id == yaml_id
                and project.cluster == cluster
                and project.org_name == org_name
                and (owner is None or project.owner == owner)
                and project.project_name == project_name
            ):
                return InMemoryProjectStorage(project.id, self._db)
        return InMemoryProjectStorage("fake-id", self._db)

    def bake(self, *, id: str) -> "BakeStorage":
        return InMemoryBakeStorage(id, self._db)

    async def create_project(
        self,
        yaml_id: str,
        project_name: str,
        cluster: Optional[str] = None,
        org_name: Optional[str] = None,
    ) -> Project:
        project = Project(
            id=_make_id(),
            project_name=project_name,
            yaml_id=yaml_id,
            cluster=cluster or self._cluster,
            owner=self._owner,
            org_name=org_name or self._org_name,
        )
        self._db.projects[project.id] = project
        return project

    async def list_projects(
        self,
        name: Optional[str] = None,
        cluster: Optional[str] = None,
        project_name: Optional[str] = None,
        org_name: Optional[str] = None,
    ) -> AsyncIterator[Project]:
        for project in self._db.projects.values():
            if name and project.yaml_id != name:
                continue
            if cluster and project.cluster != cluster:
                continue
            if project_name and project.project_name != project_name:
                continue
            if org_name and project.org_name != org_name:
                continue
            yield project


class InMemoryProjectStorage(ProjectStorage):
    def __init__(self, project_id: str, db: InMemoryDB) -> None:
        self._project_id = project_id
        self._db = db

    async def get(self) -> Project:
        try:
            return self._db.projects[self._project_id]
        except KeyError:
            raise ResourceNotFound

    async def delete(self) -> None:
        self._db.projects.pop(self._project_id)

    async def list_bakes(
        self,
        tags: Optional[AbstractSet[str]] = None,
        since: Optional[datetime.datetime] = None,
        until: Optional[datetime.datetime] = None,
        recent_first: bool = False,
    ) -> AsyncIterator[Bake]:
        unsorted: List[Bake] = []
        for bake in self._db.bakes.values():
            if bake.project_id != self._project_id:
                continue
            if tags is not None and not set(tags).issubset(set(bake.tags)):
                continue
            if since is not None and bake.created_at <= since:
                continue
            if until is not None and bake.created_at >= until:
                continue
            last_attempt: Optional[Attempt] = None
            try:
                last_attempt = await self.bake(id=bake.id).last_attempt().get()
            except ResourceNotFound:
                pass
            unsorted.append(replace(bake, last_attempt=last_attempt))
        res = sorted(unsorted, key=lambda it: it.created_at)
        if recent_first:
            res = list(reversed(res))
        for item in res:
            yield item

    async def create_bake(
        self,
        batch: str,
        meta: BakeMeta,
        graphs: Mapping[FullID, Mapping[FullID, AbstractSet[FullID]]],
        params: Optional[Mapping[str, str]] = None,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
    ) -> Bake:
        bake = Bake(
            id=_make_id(),
            project_id=self._project_id,
            batch=batch,
            graphs=graphs,
            params=params,
            name=name,
            tags=tags,
            created_at=_now(),
            last_attempt=None,
            meta=meta,
        )
        self._db.bakes[bake.id] = bake
        return bake

    def bake(
        self, *, id: Optional[str] = None, name: Optional[str] = None
    ) -> "BakeStorage":
        if id:
            return InMemoryBakeStorage(id, self._db)
        else:
            bakes: List[Bake] = []
            for bake in self._db.bakes.values():
                if bake.name == name and bake.project_id == self._project_id:
                    bakes.append(bake)
            bakes.sort(key=lambda it: it.created_at)
            if bakes:
                return InMemoryBakeStorage(bakes[-1].id, self._db)
        return InMemoryBakeStorage("fake-id", self._db)  # Error should be lazy

    async def create_cache_entry(
        self,
        task_id: FullID,
        batch: str,
        key: str,
        outputs: Mapping[str, str],
        state: Mapping[str, str],
        raw_id: str,
    ) -> CacheEntry:
        entry = CacheEntry(
            id=_make_id(),
            project_id=self._project_id,
            batch=batch,
            task_id=task_id,
            key=key,
            created_at=_now(),
            outputs=outputs,
            state=state,
            raw_id=raw_id,
        )
        self._db.cache_entries[entry.id] = entry
        return entry

    async def delete_cache_entries(
        self, batch: Optional[str] = None, task_id: Optional[FullID] = None
    ) -> None:
        if batch is None:
            self._db.cache_entries.clear()
        for entry in list(self._db.cache_entries.values()):
            if entry.batch == batch and (task_id is None or entry.task_id == task_id):
                self._db.cache_entries.pop(entry.id)

    def cache_entry(
        self,
        *,
        id: Optional[str] = None,
        task_id: Optional[FullID] = None,
        batch: Optional[str] = None,
        key: Optional[str] = None,
    ) -> "CacheEntryStorage":
        if id:
            return InMemoryCacheEntryStorage(id, self._db)
        for entry in self._db.cache_entries.values():
            if (
                entry.project_id == self._project_id
                and entry.task_id == task_id
                and entry.batch == batch
                and entry.key == key
            ):
                return InMemoryCacheEntryStorage(entry.id, self._db)
        return InMemoryCacheEntryStorage("fake-id", self._db)  # Error should be lazy

    async def list_live_jobs(self) -> AsyncIterator[LiveJob]:
        for live_job in self._db.live_jobs.values():
            if live_job.project_id == self._project_id:
                yield live_job

    async def create_live_job(
        self,
        yaml_id: str,
        multi: bool,
        tags: Iterable[str],
        raw_id: Optional[str] = None,
    ) -> LiveJob:
        live_job = LiveJob(
            id=_make_id(),
            project_id=self._project_id,
            yaml_id=yaml_id,
            multi=multi,
            tags=list(tags),
            raw_id=raw_id,
        )
        self._db.live_jobs[live_job.id] = live_job
        return live_job

    async def replace_live_job(
        self,
        yaml_id: str,
        multi: bool,
        tags: Iterable[str],
        raw_id: Optional[str] = None,
    ) -> LiveJob:
        try:
            live_job_id = (await self.live_job(yaml_id=yaml_id).get()).id
        except ResourceNotFound:
            return await self.create_live_job(yaml_id, multi, tags, raw_id)
        else:
            live_job = LiveJob(
                id=live_job_id,
                project_id=self._project_id,
                yaml_id=yaml_id,
                multi=multi,
                tags=list(tags),
                raw_id=raw_id,
            )
            self._db.live_jobs[live_job_id] = live_job
            return live_job

    def live_job(
        self, *, id: Optional[str] = None, yaml_id: Optional[str] = None
    ) -> "LiveJobStorage":
        if id:
            return InMemoryLiveJobStorage(id, self._db)
        else:
            for live_job in self._db.live_jobs.values():
                if (
                    live_job.yaml_id == yaml_id
                    and live_job.project_id == self._project_id
                ):
                    return InMemoryLiveJobStorage(live_job.id, self._db)
        return InMemoryLiveJobStorage("fake-id", self._db)  # Error should be lazy


class InMemoryBakeStorage(BakeStorage):
    def __init__(self, bake_id: str, db: InMemoryDB) -> None:
        self._bake_id = bake_id
        self._db = db

    async def get(self) -> Bake:
        try:
            return self._db.bakes[self._bake_id]
        except KeyError:
            raise ResourceNotFound

    async def list_attempts(self) -> AsyncIterator[Attempt]:
        for attempt in self._db.attempts.values():
            if attempt.bake_id == self._bake_id:
                yield attempt

    async def create_attempt(
        self,
        configs_meta: ConfigsMeta,
        number: Optional[int] = None,
        executor_id: Optional[str] = None,
        result: TaskStatus = TaskStatus.PENDING,
    ) -> Attempt:
        attempts_cnt = len([_ async for _ in self.list_attempts()])
        attempt = Attempt(
            id=_make_id(),
            bake_id=self._bake_id,
            configs_meta=configs_meta,
            number=number or attempts_cnt + 1,
            executor_id=executor_id,
            result=result,
            created_at=_now(),
        )
        self._db.attempts[attempt.id] = attempt
        return attempt

    async def create_config_file(self, filename: str, content: str) -> ConfigFile:
        config_file = ConfigFile(
            id=_make_id(),
            bake_id=self._bake_id,
            filename=filename,
            content=content,
        )
        self._db.config_files[config_file.id] = config_file
        return config_file

    async def list_bake_images(self) -> AsyncIterator[BakeImage]:
        for bake_image in self._db.bake_images.values():
            if bake_image.bake_id == self._bake_id:
                yield bake_image

    async def create_bake_image(
        self,
        yaml_defs: Sequence[FullID],
        ref: str,
        status: ImageStatus = ImageStatus.PENDING,
        context_on_storage: Optional[URL] = None,
        dockerfile_rel: Optional[str] = None,
        builder_job_id: Optional[str] = None,
    ) -> BakeImage:
        bake_image = BakeImage(
            id=_make_id(),
            ref=ref,
            bake_id=self._bake_id,
            yaml_defs=yaml_defs,
            status=status,
            context_on_storage=context_on_storage,
            dockerfile_rel=dockerfile_rel,
            builder_job_id=builder_job_id,
        )
        self._db.bake_images[bake_image.id] = bake_image
        return bake_image

    def attempt(
        self, *, id: Optional[str] = None, number: Optional[int] = None
    ) -> "AttemptStorage":
        if id:
            return InMemoryAttemptStorage(id, self._db)
        else:
            if number == -1:
                for attempt in self._db.attempts.values():
                    if attempt.bake_id == self._bake_id:
                        number = max(number, attempt.number)
            for attempt in self._db.attempts.values():
                if attempt.number == number and attempt.bake_id == self._bake_id:
                    return InMemoryAttemptStorage(attempt.id, self._db)
        return InMemoryAttemptStorage("fake-id", self._db)  # Error should be lazy

    def config_file(self, *, id: str) -> "ConfigFileStorage":
        return InMemoryConfigFileStorage(id, self._db)

    def bake_image(
        self, *, id: Optional[str] = None, ref: Optional[str] = None
    ) -> "BakeImageStorage":
        if id:
            return InMemoryBakeImageStorage(id, self._db)
        else:
            for image in self._db.bake_images.values():
                if image.ref == ref and image.bake_id == self._bake_id:
                    return InMemoryBakeImageStorage(image.id, self._db)
        return InMemoryBakeImageStorage("fake-id", self._db)  # Error should be lazy


class InMemoryAttemptStorage(AttemptStorage):
    def __init__(self, attempt_id: str, db: InMemoryDB):
        self._db = db
        self._attempt_id = attempt_id

    async def get(self) -> Attempt:
        try:
            return self._db.attempts[self._attempt_id]
        except KeyError:
            raise ResourceNotFound

    async def update(
        self,
        *,
        executor_id: Union[Optional[str], Type[_Unset]] = _Unset,
        result: Union[TaskStatus, Type[_Unset]] = _Unset,
    ) -> Attempt:
        attempt = await self.get()
        if executor_id is not _Unset:
            attempt = replace(
                attempt, executor_id=executor_id  # type: ignore[arg-type]
            )
        if result is not _Unset:
            attempt = replace(attempt, result=result)  # type: ignore[arg-type]
        self._db.attempts[attempt.id] = attempt
        return attempt

    async def list_tasks(self) -> AsyncIterator[Task]:
        for task in self._db.tasks.values():
            if task.attempt_id == self._attempt_id:
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
        task = Task(
            id=_make_id(),
            attempt_id=self._attempt_id,
            yaml_id=yaml_id,
            raw_id=raw_id,
            outputs=outputs,
            state=state,
            statuses=[status],
        )
        self._db.tasks[task.id] = task
        return task

    def task(
        self, *, id: Optional[str] = None, yaml_id: Optional[FullID] = None
    ) -> "TaskStorage":
        if id:
            return InMemoryTaskStorage(id, self._db)
        else:
            for task in self._db.tasks.values():
                if task.yaml_id == yaml_id and task.attempt_id == self._attempt_id:
                    return InMemoryTaskStorage(task.id, self._db)
        return InMemoryTaskStorage("fake-id", self._db)  # Error should be lazy


class InMemoryTaskStorage(TaskStorage):
    def __init__(self, task_id: str, db: InMemoryDB):
        self._db = db
        self._task_id = task_id

    async def get(self) -> Task:
        try:
            return self._db.tasks[self._task_id]
        except KeyError:
            raise ResourceNotFound

    async def update(
        self,
        *,
        outputs: Union[Optional[Mapping[str, str]], Type[_Unset]] = _Unset,
        state: Union[Optional[Mapping[str, str]], Type[_Unset]] = _Unset,
        new_status: Optional[Union[TaskStatusItem, TaskStatus]] = None,
    ) -> Task:
        task = await self.get()
        if outputs is not _Unset:
            task = replace(task, outputs=outputs)  # type: ignore[arg-type]
        if state is not _Unset:
            task = replace(task, state=state)  # type: ignore[arg-type]
        if isinstance(new_status, TaskStatus):
            new_status = TaskStatusItem(when=_now(), status=new_status)
        if new_status:
            task = replace(task, statuses=[*task.statuses, new_status])
        self._db.tasks[task.id] = task
        return task


class InMemoryConfigFileStorage(ConfigFileStorage):
    def __init__(self, config_file_id: str, db: InMemoryDB):
        self._db = db
        self._config_file_id = config_file_id

    async def get(self) -> ConfigFile:
        try:
            return self._db.config_files[self._config_file_id]
        except KeyError:
            raise ResourceNotFound


class InMemoryBakeImageStorage(BakeImageStorage):
    def __init__(self, bake_image_id: str, db: InMemoryDB):
        self._db = db
        self._bake_image_id = bake_image_id

    async def get(self) -> BakeImage:
        try:
            return self._db.bake_images[self._bake_image_id]
        except KeyError:
            raise ResourceNotFound

    async def update(
        self,
        *,
        status: Union[ImageStatus, Type[_Unset]] = _Unset,
        builder_job_id: Union[Optional[str], Type[_Unset]] = _Unset,
    ) -> BakeImage:
        image = await self.get()
        if status is not _Unset:
            image = replace(image, status=status)  # type: ignore[arg-type]
        if builder_job_id is not _Unset:
            image = replace(
                image, builder_job_id=builder_job_id  # type: ignore[arg-type]
            )
        self._db.bake_images[image.id] = image
        return image


class InMemoryCacheEntryStorage(CacheEntryStorage):
    def __init__(self, cache_entry_id: str, db: InMemoryDB):
        self._db = db
        self._cache_entry_id = cache_entry_id

    async def get(self) -> CacheEntry:
        try:
            return self._db.cache_entries[self._cache_entry_id]
        except KeyError:
            raise ResourceNotFound


class InMemoryLiveJobStorage(LiveJobStorage):
    def __init__(self, live_job_id: str, db: InMemoryDB):
        self._db = db
        self._live_job_id = live_job_id

    async def get(self) -> LiveJob:
        try:
            return self._db.live_jobs[self._live_job_id]
        except KeyError:
            raise ResourceNotFound
