from dataclasses import dataclass

import logging
import os
import pathlib
import pytest
import secrets
import shutil
import subprocess
from datetime import datetime, timedelta
from neuro_sdk import login_with_token
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
from yarl import URL


log = logging.getLogger(__name__)


@pytest.fixture
def assets() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "assets"


@pytest.fixture
def project_id() -> str:
    return f"e2e_proj_{make_image_date_flag()}_{secrets.token_hex(10)}"


@pytest.fixture
def ws(assets: pathlib.Path, tmp_path_factory: Any, project_id: str) -> pathlib.Path:
    tmp_dir: pathlib.Path = tmp_path_factory.mktemp("proj-dir-parent")
    ws_dir = tmp_dir / project_id
    shutil.copytree(assets / "ws", ws_dir)
    (ws_dir / "project.yml").write_text(f"id: {project_id}")
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


RunCLI = Callable[[List[str]], SysCap]


@pytest.fixture
def _run_cli(
    loop: None, ws: pathlib.Path, api_config: Optional[pathlib.Path]
) -> RunCLI:
    def _run(
        arguments: List[str],
    ) -> SysCap:
        if api_config:
            os.environ["NEUROMATION_CONFIG"] = str(api_config)
        proc = subprocess.run(
            arguments,
            timeout=600,
            cwd=ws,
            encoding="utf8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            proc.check_returncode()
        except subprocess.CalledProcessError:
            log.error(f"Last stdout: '{proc.stdout}'")
            log.error(f"Last stderr: '{proc.stderr}'")
            raise
        return SysCap(out=proc.stdout.strip(), err=proc.stderr.strip())

    return _run


@pytest.fixture
def run_cli(_run_cli: RunCLI) -> RunCLI:
    return lambda args: _run_cli(["neuro-flow", "--show-traceback"] + args)


@pytest.fixture
def run_neuro_cli(_run_cli: RunCLI) -> RunCLI:
    return lambda args: _run_cli(["neuro", "--show-traceback"] + args)


IMAGE_DATETIME_FORMAT = "%Y%m%d%H%M"
IMAGE_DATETIME_SEP = "_date"


def make_image_date_flag() -> str:
    time_str = datetime.now().strftime(IMAGE_DATETIME_FORMAT)
    return f"{IMAGE_DATETIME_SEP}{time_str}{IMAGE_DATETIME_SEP}"


@pytest.fixture(scope="session")
def _drop_once_flag() -> Dict[str, bool]:
    return {}


@pytest.fixture(autouse=True)
def drop_old_test_images(
    run_neuro_cli: RunCLI, _drop_once_flag: Dict[str, bool]
) -> None:
    if _drop_once_flag.get("cleaned"):
        return

    res: SysCap = run_neuro_cli(["-q", "image", "ls", "--full-uri"])
    for image_str in res.out.splitlines():
        image_str = image_str.strip()
        image_url = URL(image_str)
        image_name = image_url.parts[-1]
        try:
            _, time_str, _ = image_name.split(IMAGE_DATETIME_SEP)
            image_time = datetime.strptime(time_str, IMAGE_DATETIME_FORMAT)
            if datetime.now() - image_time < timedelta(days=1):
                continue
            run_neuro_cli(["image", "rm", image_str])
        except Exception:
            pass

    _drop_once_flag["cleaned"] = True
