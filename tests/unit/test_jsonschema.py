from dataclasses import dataclass

import pytest
import yaml
from importlib.resources import open_text
from itertools import chain
from json import load
from jsonschema import validate
from pathlib import Path

import apolo_flow


JSON = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]


@dataclass
class Schemas:
    flow: dict[str, JSON]
    project: dict[str, JSON]


@pytest.fixture(scope="module")
def schemas() -> Schemas:
    with open_text(apolo_flow, "flow-schema.json") as f:
        flow_schema = load(f)

    with open_text(apolo_flow, "project-schema.json") as f:
        project_schema = load(f)

    return Schemas(flow_schema, project_schema)


def test_all_yamls(yaml_file: Path, schemas: Schemas) -> None:
    yml = yaml.safe_load(yaml_file.read_text())
    if yaml_file.stem in ("project", "minimal_project", "with_pname_project"):
        validate(instance=yml, schema=schemas.project)
    else:
        validate(instance=yml, schema=schemas.flow)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "yaml_file" not in metafunc.fixturenames:
        return
    here = Path(__file__)
    toplevel = here.parent.parent.parent
    params = []
    for fname in chain(toplevel.glob("**/*.yml"), toplevel.glob("**/*.yaml")):
        if ".github" in fname.parts:
            continue
        if fname.name.startswith("."):
            continue
        params.append(pytest.param(fname, id=str(fname.relative_to(toplevel))))
    metafunc.parametrize("yaml_file", params)
