import pytest
import socket
import sys
from neuro_sdk import Client
from pathlib import Path

from neuro_flow.config_loader import LiveLocalCL
from neuro_flow.parser import find_workspace


async def test_not_exists(tmp_path: Path, client: Client) -> None:
    d = tmp_path / ".neuro"
    d.mkdir()
    with pytest.raises(ValueError, match="Config file for flow '.+' not found .+"):
        LiveLocalCL(find_workspace(d), client).flow_path("live")


def test_neuro_not_found(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError, match=r"\.neuro folder was not found in lookup for .+"
    ):
        find_workspace(tmp_path)


@pytest.mark.skipif(
    sys.platform == "win32", reason="UNIX sockets are not supported by Windows"
)
@pytest.mark.skipif(
    sys.platform == "darwin", reason="MacOS doesn't support too long UNIX socket names"
)
def test_not_a_file_explicit(tmp_path: Path) -> None:
    f = tmp_path / "file.sock"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(f))

    with pytest.raises(ValueError, match=r".+ should be a directory"):
        find_workspace(f)


@pytest.mark.skipif(
    sys.platform == "win32", reason="UNIX sockets are not supported by Windows"
)
@pytest.mark.skipif(
    sys.platform == "darwin", reason="MacOS doesn't support too long UNIX socket names"
)
async def test_not_a_file_implicit(tmp_path: Path, client: Client) -> None:
    d = tmp_path / ".neuro"
    d.mkdir()
    f = d / "live.yml"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(f))

    with pytest.raises(ValueError, match=r".+ is not a file"):
        LiveLocalCL(find_workspace(d), client).flow_path("live")


def test_explicit_file(tmp_path: Path) -> None:
    f = tmp_path / "file.yml"
    f.touch()

    with pytest.raises(ValueError, match=r".+ should be a directory"):
        find_workspace(f)


async def test_found(tmp_path: Path, client: Client) -> None:
    d = tmp_path / ".neuro"
    d.mkdir()
    f = d / "live.yml"
    f.touch()

    assert f == LiveLocalCL(find_workspace(d), client).flow_path("live")
