import pathlib
import pytest


@pytest.fixture  # type: ignore
def assets() -> pathlib.Path:
    return pathlib.Path(__file__).parent
