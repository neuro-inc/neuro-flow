import pathlib

from neuro_flow import ast
from neuro_flow.parser import parse


def test_parse_minimal(assets: pathlib.Path) -> None:
    flow = parse(assets / "jobs-minimal.yml")
    assert flow == ast.InteractiveFlow(
        kind=ast.Kind.JOB,
        title=None,
        images=[],
        volumes=[],
        tags=set(),
        env={},
        workdir=None,
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
                volumes=[],
                tags=set(),
                life_span=None,
                title=None,
                detach=False,
                browse=False,
            )
        },
    )


def test_parse_workdir(assets: pathlib.Path) -> None:
    flow = parse(assets / "jobs-workdir.yml")
    assert flow == ast.InteractiveFlow(
        kind=ast.Kind.JOB,
        title=None,
        images=[],
        volumes=[],
        tags=set(),
        env={},
        workdir=pathlib.PurePosixPath("/main/dir"),
        jobs={
            "test": ast.Job(
                id="test",
                name=None,
                image="ubuntu",
                preset=None,
                http=None,
                entrypoint=None,
                cmd="echo abc",
                workdir=pathlib.PurePosixPath("/real/folder"),
                env={},
                volumes=[],
                tags=set(),
                life_span=None,
                title=None,
                detach=False,
                browse=False,
            )
        },
    )


def test_parse_title(assets: pathlib.Path) -> None:
    flow = parse(assets / "jobs-title.yml")
    assert flow == ast.InteractiveFlow(
        kind=ast.Kind.JOB,
        title="Global title",
        images=[],
        volumes=[],
        tags=set(),
        env={},
        workdir=None,
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
                volumes=[],
                tags=set(),
                life_span=None,
                title="Job title",
                detach=False,
                browse=False,
            )
        },
    )
