from dataclasses import dataclass

import pytest
import sys
import yaml
from importlib.resources import open_text
from itertools import chain
from json import load
from jsonschema import ValidationError, validate
from pathlib import Path
from typing import Union

import apolo_flow


JSON = Union[None, bool, int, float, str, list["JSON"], dict[str, "JSON"]]


@dataclass
class Schemas:
    action: dict[str, JSON]
    flow: dict[str, JSON]
    project: dict[str, JSON]


@pytest.fixture(scope="module")
def schemas() -> Schemas:
    with open_text(apolo_flow, "action-schema.json") as f:
        action_schema = load(f)

    with open_text(apolo_flow, "flow-schema.json") as f:
        flow_schema = load(f)

    with open_text(apolo_flow, "project-schema.json") as f:
        project_schema = load(f)

    return Schemas(action_schema, flow_schema, project_schema)


@pytest.mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup required")
def test_all_yamls(yaml_file: Path, schemas: Schemas) -> None:
    yml = yaml.safe_load(yaml_file.read_text())
    excs = []
    for schema in (schemas.project, schemas.action, schemas.flow):
        try:
            validate(instance=yml, schema=schema)
            break
        except ValidationError as exc:
            excs.append(exc)
    else:
        raise ExceptionGroup(f"Cannot validate [{yaml_file}]", excs)


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
        if "bad" in fname.stem.split("-"):
            continue
        if "bake_meta" in fname.parts:
            continue
        params.append(pytest.param(fname, id=str(fname.relative_to(toplevel))))
    metafunc.parametrize("yaml_file", params)
