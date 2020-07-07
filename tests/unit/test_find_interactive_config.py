import socket
import sys
from pathlib import Path

import pytest

from neuro_flow.parser import find_interactive_config


def test_not_exists_explicit(tmp_path: Path) -> None:
    f = tmp_path / "file.yml"
    with pytest.raises(ValueError, match=".+ does not exist"):
        find_interactive_config(f)


def test_not_exists_implicit(tmp_path: Path) -> None:
    d = tmp_path / ".neuro"
    d.mkdir()
    with pytest.raises(ValueError, match=".+ does not exist"):
        find_interactive_config(d)


def test_neuro_not_found(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError, match=r"\.neuro folder was not found in lookup for .+"
    ):
        find_interactive_config(tmp_path)


@pytest.mark.skipif(  # type: ignore
    sys.platform == "win32", reason="UNIX sockets are not supported by Windows"
)
def test_not_a_file_explicit(tmp_path: Path) -> None:
    f = tmp_path / "file.sock"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(f))

    with pytest.raises(ValueError, match=r".+ should be a file or directory"):
        find_interactive_config(f)


@pytest.mark.skipif(  # type: ignore
    sys.platform == "win32", reason="UNIX sockets are not supported by Windows"
)
def test_not_a_file_implicit(tmp_path: Path) -> None:
    d = tmp_path / ".neuro"
    d.mkdir()
    f = d / "jobs.yml"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(f))

    with pytest.raises(ValueError, match=r".+ is not a file"):
        find_interactive_config(d)


def test_found_explicit(tmp_path: Path) -> None:
    f = tmp_path / "file.yml"
    f.touch()

    assert f == find_interactive_config(f)


def test_found_implicit(tmp_path: Path) -> None:
    d = tmp_path / ".neuro"
    d.mkdir()
    f = d / "jobs.yml"
    f.touch()

    assert f == find_interactive_config(d)
