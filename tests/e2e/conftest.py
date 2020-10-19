from dataclasses import dataclass

import logging
import os
import pathlib
import pytest
import subprocess
from neuromation.api import login_with_token
from typing import Any, AsyncIterator, Callable, List, Optional
from yarl import URL


log = logging.getLogger(__name__)


@pytest.fixture
def assets() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "assets"


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
def run_cli(
    loop: None, assets: pathlib.Path, api_config: Optional[pathlib.Path]
) -> RunCLI:
    def _run(
        arguments: List[str],
    ) -> SysCap:
        if api_config:
            os.environ["NEUROMATION_CONFIG"] = str(api_config)
        proc = subprocess.run(
            ["neuro-flow"] + arguments,
            timeout=300,
            cwd=assets / "ws",
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
