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
import sys
from apolo_sdk import Config, get as api_get, login_with_token
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional
from yarl import URL


NETWORK_TIMEOUT = 3 * 60.0
CLIENT_TIMEOUT = aiohttp.ClientTimeout(None, None, NETWORK_TIMEOUT, NETWORK_TIMEOUT)

log = logging.getLogger(__name__)


@pytest.fixture
def assets() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "assets"


@pytest.fixture
def project_id() -> str:
    return f"e2e_proj_{secrets.token_hex(6)}_{make_date_flag()}"


async def get_config(nmrc_path: Optional[Path]) -> Config:
    __tracebackhide__ = True
    cluster = os.environ.get("E2E_CLUSTER")
    async with api_get(timeout=CLIENT_TIMEOUT, path=nmrc_path) as client:
        if cluster:
            await client.config.switch_cluster(cluster)
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
def project_name(api_config_data: Config) -> str:
    return api_config_data.project_name_or_raise


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
    (ws_dir / ".apolo" / "project.yml").write_text(project_data)
    return ws_dir


@pytest.fixture
async def api_config(tmp_path_factory: Any) -> AsyncIterator[Optional[pathlib.Path]]:
    e2e_test_token = os.environ.get("E2E_USER_TOKEN")
    e2e_test_api_endpoint = os.environ.get(
        "E2E_API_ENDPOINT", "https://api.dev.apolo.us/api/v1"
    )
    if e2e_test_token:
        tmp_path = tmp_path_factory.mktemp("config")
        config_path = tmp_path / "conftest"
        await login_with_token(
            e2e_test_token,
            url=URL(e2e_test_api_endpoint),
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
def _run_cli(ws: pathlib.Path, api_config: Optional[pathlib.Path]) -> RunCLI:
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
    return lambda args: _run_cli(["apolo-flow", "--show-traceback"] + args)


@pytest.fixture
def run_apolo_cli(_run_cli: RunCLI) -> RunCLI:
    return lambda args: _run_cli(["apolo", "--show-traceback"] + args)


DATETIME_FORMAT = "%Y%m%d%H%M"
DATETIME_SEP = "date"


def make_date_flag() -> str:
    time_str = datetime.now().strftime(DATETIME_FORMAT)
    return f"{DATETIME_SEP}{time_str}{DATETIME_SEP}"


@pytest.fixture(scope="session")
def _drop_once_flag() -> Dict[str, bool]:
    return {}


# TODO: turn on back image cleanup when fixed
# https://github.com/neuro-inc/neuro-cli/issues/2913
# @pytest.fixture(autouse=True)
async def drop_old_test_images(
    run_apolo_cli: RunCLI, _drop_once_flag: Dict[str, bool]
) -> None:
    if _drop_once_flag.get("cleaned_images"):
        return

    if sys.version_info < (3, 8) and sys.platform == "win32":
        # Default selector-based event loop for Windows doesn't support subprocesses
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
            await run_apolo_cli(["image", "rm", image_str])
        except Exception:
            pass

    res: SysCap = await run_apolo_cli(["-q", "image", "ls", "--full-uri"])

    tasks = []
    for image_str in res.out.splitlines():
        tasks.append(asyncio.create_task(_drop_iamge(image_str)))

    if tasks:
        await asyncio.wait(tasks)

    _drop_once_flag["cleaned_images"] = True


@pytest.fixture(autouse=True)
async def drop_old_roles(
    run_apolo_cli: RunCLI, _drop_once_flag: Dict[str, bool], username: str
) -> None:
    if _drop_once_flag.get("cleaned_roles"):
        return

    res: SysCap = await run_apolo_cli(
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
            await run_apolo_cli(
                ["acl", "remove-role", f"{username}/projects/{role_name}"]
            )
        except Exception:
            pass

    tasks = []
    for project in res.out.splitlines():
        tasks.append(asyncio.create_task(_drop_role(project)))

    if tasks:
        await asyncio.wait(tasks)

    _drop_once_flag["cleaned_roles"] = True
