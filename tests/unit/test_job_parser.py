import pathlib

from neuromation.api import HTTPPort
from yarl import URL

from neuro_flow import ast
from neuro_flow.parser import parse


def test_parse_minimal(assets: pathlib.Path) -> None:
    flow = parse(assets / "jobs-minimal.yml")
    assert flow == ast.InteractiveFlow(
        kind=ast.Kind.JOB,
        title=None,
        images={},
        volumes={},
        tags=set(),
        env={},
        workdir=None,
        life_span=None,
        jobs={
            "test": ast.Job(
                id="test",
                name=None,
                image="ubuntu",
                preset=None,
                http=None,
                entrypoint=None,
                cmd="echo abc",
                workdir=None,
                env={},
                volumes=(),
                tags=set(),
                life_span=None,
                title=None,
                detach=False,
                browse=False,
            )
        },
    )


def test_parse_full(assets: pathlib.Path) -> None:
    flow = parse(assets / "jobs-full.yml")
    assert flow == ast.InteractiveFlow(
        kind=ast.Kind.JOB,
        title="Global title",
        images={
            "image_a": ast.Image(
                id="image_a",
                uri=URL("image:banana"),
                context=pathlib.Path("dir/context"),
                dockerfile=pathlib.Path("dir/Dockerfile"),
                build_args={"arg1": "val1", "arg2": "val2"},
            )
        },
        volumes={
            "volume_a": ast.Volume(
                id="volume_a",
                uri=URL("storage:dir"),
                mount=pathlib.PurePosixPath("/var/dir"),
                ro=True,
            )
        },
        tags={"tag-a", "tag-b"},
        env={"global_a": "val-a", "global_b": "val-b"},
        workdir=pathlib.PurePosixPath("/global/dir"),
        life_span=100800.0,
        jobs={
            "test": ast.Job(
                id="test",
                name="job-name",
                image="${{ images.image_a.ref }}",
                preset="cpu-small",
                http=HTTPPort(port=8080, requires_auth=False),
                entrypoint="bash",
                cmd="echo abc",
                workdir=pathlib.PurePosixPath("/local/dir"),
                env={"local_a": "val-1", "local_b": "val-2"},
                volumes=("${{ volumes.volume_a.ref }}", "storage:dir:/var/dir:ro"),
                tags={"tag-2", "tag-1"},
                life_span=10500.0,
                title="Job title",
                detach=True,
                browse=True,
            )
        },
    )
