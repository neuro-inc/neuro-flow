import pathlib

import pytest


@pytest.fixture
def assets() -> pathlib.Path:
    return pathlib.Path(__file__).parent
