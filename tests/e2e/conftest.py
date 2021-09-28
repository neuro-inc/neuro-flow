from dataclasses import dataclass

import aiohttp
import asyncio
import logging
import os
import pathlib
import pytest
import secrets
import shutil
import subprocess
from datetime import datetime, timedelta
from neuro_sdk import Config, get as api_get, login_with_token
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
)
from yarl import URL

from neuro_flow.context import sanitize_name


NETWORK_TIMEOUT = 3 * 60.0
CLIENT_TIMEOUT = aiohttp.ClientTimeout(None, None, NETWORK_TIMEOUT, NETWORK_TIMEOUT)

log = logging.getLogger(__name__)


@pytest.fixture
def loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()


@pytest.fixture
def assets() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "assets"


@pytest.fixture
def project_id() -> str:
    return f"e2e_proj_{secrets.token_hex(6)}_{make_date_flag()}"


async def get_config(nmrc_path: Optional[Path]) -> Config:
    __tracebackhide__ = True
    async with api_get(timeout=CLIENT_TIMEOUT, path=nmrc_path) as client:
        return client.config


@pytest.fixture
async def api_config_data(api_config: Optional[pathlib.Path]) -> Config:
    return await get_config(api_config)


@pytest.fixture
def username(api_config_data: Config) -> str:
    return api_config_data.username


@pytest.fixture
def cluster_name(api_config_data: Config) -> str:
    return api_config_data.cluster_name


@pytest.fixture
async def project_role(
    project_id: str, username: str, run_neuro_cli: "RunCLI"
) -> AsyncIterator[str]:
    project_role = f"{username}/projects/{sanitize_name(project_id)}"
    try:
        yield project_role
    finally:
        await run_neuro_cli(["acl", "remove-role", project_role])


@pytest.fixture
def ws(
    assets: pathlib.Path,
    tmp_path_factory: Any,
    project_id: str,
    username: str,
) -> pathlib.Path:
    tmp_dir: pathlib.Path = tmp_path_factory.mktemp("proj-dir-parent")
    ws_dir = tmp_dir / project_id
    shutil.copytree(assets / "ws", ws_dir)
    project_data = f"id: {project_id}"
    if username:
        project_data += f'\nowner: "{username}"'
    (ws_dir / ".neuro" / "project.yml").write_text(project_data)
    return ws_dir


@pytest.fixture
async def api_config(tmp_path_factory: Any) -> AsyncIterator[Optional[pathlib.Path]]:
    e2e_test_token = os.environ.get("E2E_USER_TOKEN")
    if e2e_test_token:
        tmp_path = tmp_path_factory.mktemp("config")
        config_path = tmp_path / "conftest"
        await login_with_token(
            e2e_test_token,
            url=URL("https://dev.neu.ro/api/v1"),
            path=config_path,
        )
    else:
        config_path = None
    yield config_path


@dataclass(frozen=True)
class SysCap:
    out: str
    err: str


RunCLI = Callable[[List[str]], Awaitable[SysCap]]


@pytest.fixture
def _run_cli(
    loop: None, ws: pathlib.Path, api_config: Optional[pathlib.Path]
) -> RunCLI:
    async def _run(
        arguments: List[str],
    ) -> SysCap:
        if api_config:
            os.environ["NEUROMATION_CONFIG"] = str(api_config)
        proc = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=ws,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdout
        assert proc.stderr
        ret_code = await asyncio.wait_for(proc.wait(), timeout=600)
        out = (await proc.stdout.read()).decode(
            encoding="utf8",
            errors="replace",
        )
        err = (await proc.stderr.read()).decode(
            encoding="utf8",
            errors="replace",
        )
        if ret_code:
            log.error(f"Last stdout: '{out}'")
            log.error(f"Last stderr: '{err}'")
            raise subprocess.CalledProcessError(ret_code, arguments[0], out, err)
        return SysCap(out=out.strip(), err=err.strip())

    return _run


@pytest.fixture
def run_cli(_run_cli: RunCLI) -> RunCLI:
    return lambda args: _run_cli(["neuro-flow", "--show-traceback"] + args)


@pytest.fixture
def run_neuro_cli(_run_cli: RunCLI) -> RunCLI:
    return lambda args: _run_cli(["neuro", "--show-traceback"] + args)


DATETIME_FORMAT = "%Y%m%d%H%M"
DATETIME_SEP = "date"


def make_date_flag() -> str:
    time_str = datetime.now().strftime(DATETIME_FORMAT)
    return f"{DATETIME_SEP}{time_str}{DATETIME_SEP}"


@pytest.fixture(scope="session")
def _drop_once_flag() -> Dict[str, bool]:
    return {}


@pytest.fixture(autouse=True)
async def drop_old_test_images(
    run_neuro_cli: RunCLI, _drop_once_flag: Dict[str, bool]
) -> None:
    if _drop_once_flag.get("cleaned_images"):
        return

    async def _drop_iamge(image_str: str) -> None:
        image_str = image_str.strip()
        image_url = URL(image_str)
        image_name = image_url.parts[-1]
        try:
            _, time_str, _ = image_name.split(DATETIME_SEP)
            image_time = datetime.strptime(time_str, DATETIME_FORMAT)
            if datetime.now() - image_time < timedelta(days=1):
                return
            await run_neuro_cli(["image", "rm", image_str])
        except Exception:
            pass

    res: SysCap = await run_neuro_cli(["-q", "image", "ls", "--full-uri"])

    tasks = []
    for image_str in res.out.splitlines():
        tasks.append(asyncio.ensure_future(_drop_iamge(image_str)))

    if tasks:
        await asyncio.wait(tasks)

    _drop_once_flag["cleaned_images"] = True


@pytest.fixture(autouse=True)
async def drop_old_roles(
    run_neuro_cli: RunCLI, _drop_once_flag: Dict[str, bool], username: str
) -> None:
    if _drop_once_flag.get("cleaned_roles"):
        return

    res: SysCap = await run_neuro_cli(
        ["acl", "ls", "--shared", f"role://{username}/projects"]
    )

    async def _drop_role(project_str: str) -> None:
        role_str, _ = project_str.split(" ", 1)
        role_uri = URL(role_str)
        role_name = role_uri.parts[-1]
        try:
            _, time_str, _ = role_name.split(DATETIME_SEP)
            proj_time = datetime.strptime(time_str, DATETIME_FORMAT)
            if datetime.now() - proj_time < timedelta(hours=4):
                return
            await run_neuro_cli(
                ["acl", "remove-role", f"{username}/projects/{role_name}"]
            )
        except Exception:
            pass

    tasks = []
    for project in res.out.splitlines():
        tasks.append(asyncio.ensure_future(_drop_role(project)))

    if tasks:
        await asyncio.wait(tasks)

    _drop_once_flag["cleaned_roles"] = True
