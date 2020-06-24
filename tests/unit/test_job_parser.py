import pathlib

from neuro_flow import ast
from neuro_flow.parser import parse


def test_parse_minimal(assets: pathlib.Path) -> None:
    flow = parse(assets / "jobs-minimal.yml")
    assert flow == ast.InteractiveFlow(
        kind=ast.Kind.JOB,
        title="Jobs minimal",
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
                title="test",
                detach=False,
                browse=False,
            )
        },
    )
