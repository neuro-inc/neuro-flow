#!/usr/bin/env python3

from dataclasses import replace

import json
from neuro_cli.asyncio_utils import run
from neuro_sdk import (
    Client,
    FileStatus,
    IllegalArgumentError,
    ResourceNotFound,
    get as api_get,
)
from typing import AsyncIterator
from yarl import URL

from neuro_flow.storage import (
    APIStorage,
    Attempt,
    Bake,
    ConfigFile,
    FileSystem,
    FSStorage,
    NeuroStorageFS,
    Project,
    TaskStatus,
)


class FakeFS(FileSystem):
    root = URL("fake:fs")

    async def stat(self, uri: URL) -> FileStatus:
        raise NotImplementedError

    async def ls(self, uri: URL) -> AsyncIterator[FileStatus]:
        return
        yield FileStatus()

    async def mkdir(
        self, uri: URL, *, parents: bool = False, exist_ok: bool = False
    ) -> None:
        pass

    async def open(self, uri: URL) -> AsyncIterator[bytes]:
        return
        yield b""

    async def create(self, uri: URL, data: bytes) -> None:
        pass

    async def rm(self, uri: URL, *, recursive: bool = False) -> None:
        pass


async def process_attempt(
    fs: FSStorage, api: APIStorage, new_bake: Bake, attempt: Attempt
) -> None:
    try:
        new_attempt = await api.find_attempt(new_bake, attempt.number)
        print("  Attempt", attempt.number, "exists")
        if new_attempt.result not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            # attempt is fully processed
            return
    except ResourceNotFound:
        new_attempt = await api.create_attempt(new_bake, attempt.number, attempt.when)
        print("  Attempt", attempt.number, "created")
    started, finished = await fs.fetch_attempt(attempt)
    new_started, new_finished = await api.fetch_attempt(new_attempt)
    for st in started.values():
        if st.id in new_started:
            print("   Started task", ".".join(st.id), "exists")
            continue
        await api.write_start(replace(st, attempt=new_attempt))
        print("   Started task", ".".join(st.id), "created")
    for ft in finished.values():
        if ft.id in new_finished:
            print("   Finished task", ".".join(ft.id), "exists")
            continue
        await api.write_finish(replace(ft, attempt=new_attempt))
        print("   Finished task", ".".join(ft.id), "created")
    if new_attempt.result != attempt.result:
        print("  Finish attempt", attempt.number, "with", attempt.result)
        await api.finish_attempt(new_attempt, attempt.result)


async def process_bake(fs: FSStorage, api: APIStorage, bake: Bake) -> None:
    try:
        new_bake = await api.fetch_bake_by_id(bake.project, bake.bake_id)
        print(" Bake", str(bake), "exists")
    except ResourceNotFound:
        configs_meta = await fs.fetch_configs_meta(bake)
        configs = []
        fname = configs_meta["flow_config"]["storage_filename"]
        content = await fs.fetch_config(bake, fname)
        configs.append(ConfigFile(fname, content))
        if configs_meta["project_config"]:
            configs_meta["project_config"]["storage_filename"]
            content = await fs.fetch_config(bake, fname)
            configs.append(ConfigFile(fname, content))
        for item in configs_meta["action_configs"].values():
            fname = item["storage_filename"]
            content = await fs.fetch_config(bake, fname)
            configs.append(ConfigFile(fname, content))
        try:
            new_bake = await api.create_bake(
                bake.project,
                bake.batch,
                configs_meta,
                configs,
                bake.graphs,
                bake.params,
                when=bake.when,
                name=None,
                tags=(),
            )
        except IllegalArgumentError:
            print("Cannot migrate bake", str(bake))
            return
        print(" Bake", str(bake), "created")
    else:
        pass
    for attempt_no in range(1, 100):
        try:
            attempt = await fs.find_attempt(bake, attempt_no)
            await process_attempt(fs, api, new_bake, attempt)
        except ResourceNotFound:
            break


async def process_cache(
    client: Client, api: APIStorage, cache: URL, project: Project
) -> None:
    batches = []
    try:
        async for batch in client.storage.ls(cache):
            if not batch.is_dir():
                continue
            batches.append(batch.uri)
    except ResourceNotFound:
        print(" Absent cache for", cache)
    for batch in batches:
        print(" Cache", batch.name)
        async for fname in client.storage.ls(batch):
            if not fname.name.endswith(".json"):
                continue
            task_id = fname.name[:-4]
            print("  Write", task_id)
            content = []
            async for chunk in client.storage.open(fname.uri):
                content.append(chunk)
            cache_data = json.loads(b"".join(content).decode("utf-8"))
            # cache_data = {
            #     "when": ft.when.isoformat(),
            #     "caching_key": caching_key,
            #     "raw_id": ft.raw_id,
            #     "status": ft.status.value,
            #     "exit_code": None,
            #     "created_at": ft.created_at.isoformat(),
            #     "started_at": ft.started_at.isoformat(),
            #     "finished_at": ft.finished_at.isoformat(),
            #     "finish_reason": "",
            #     "finish_description": "",
            #     "outputs": ft.outputs,
            #     "state": ft.state,
            # }

        auth = await client.config._api_auth()
        async with client._core.request(
            "POST",
            client.config.api_url / "flow/cache_entries",
            json={
                "project_id": project.id,
                "task_id": task_id,
                "batch": batch.name,
                "key": cache_data["caching_key"],
                "outputs": cache_data["outputs"],
                "state": cache_data["state"],
                "created_at": cache_data["when"],
            },
            auth=auth,
        ) as resp:
            await resp.json()


async def process_project(
    client: Client, fs: FSStorage, api: APIStorage, prj: URL
) -> None:
    print("Project", prj.name)
    project = await api.ensure_project(prj.name)
    bakes = []
    async for bake in fs.list_bakes(prj.name):
        bakes.append(bake)
    for bake in bakes:
        await process_bake(fs, api, bake)
    await process_cache(client, api, prj / ".cache", project)


async def main() -> None:
    async with api_get() as client:
        fs = FSStorage(NeuroStorageFS(client))
        fake_fs = FakeFS()
        api = APIStorage(client, fake_fs)
        projects = []
        async for prj in client.storage.ls(URL("storage:.flow")):
            if not prj.is_dir():
                continue
            projects.append(prj)
        for prj in projects:
            await process_project(client, fs, api, prj.uri)


run(main())
