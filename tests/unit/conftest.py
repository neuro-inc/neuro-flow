import asyncio
import os
import pathlib
import pytest
from apolo_sdk import Client, get as api_get, login_with_token
from typing import Any, AsyncIterator, Iterator
from yarl import URL


@pytest.fixture
def assets() -> pathlib.Path:
    return pathlib.Path(__file__).parent


@pytest.fixture(scope="session")
def api_config(tmp_path_factory: Any) -> Iterator[pathlib.Path]:
    e2e_test_token = os.environ.get("E2E_USER_TOKEN")
    e2e_test_api_endpoint = "https://api.dev.apolo.us/api/v1"
    if e2e_test_token:
        tmp_path = tmp_path_factory.mktemp("config")
        config_path = tmp_path / "conftest"
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            login_with_token(
                e2e_test_token,
                url=URL(e2e_test_api_endpoint),
                path=config_path,
            )
        )
    else:
        config_path = None
    yield config_path


@pytest.fixture
async def client(api_config: pathlib.Path) -> AsyncIterator[Client]:
    cluster = os.environ.get("E2E_CLUSTER")
    async with api_get(path=api_config) as client:
        if cluster:
            await client.config.switch_cluster(cluster)
        yield client
