import os
import pathlib
import pytest
from neuromation.api import login_with_token
from typing import Any, AsyncIterator
from yarl import URL


@pytest.fixture  # type: ignore
def assets() -> pathlib.Path:
    return pathlib.Path(__file__).parent


@pytest.fixture  # type: ignore
async def api_config(tmp_path_factory: Any) -> AsyncIterator[pathlib.Path]:
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
