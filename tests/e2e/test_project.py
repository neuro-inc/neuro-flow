import pytest
from typing import Dict

from tests.e2e.conftest import RunCLI


@pytest.mark.parametrize(
    "template",
    [
        {
            "name": "barebone",
            "command": "cookiecutter gh:neuro-inc/cookiecutter-neuro-project-barebone",
        },
        {
            "name": "recommended",
            "command": "cookiecutter gh:neuro-inc/cookiecutter-neuro-project --checkout release",  # noqa
        },
    ],
    ids=lambda template: template["name"],  # type: ignore
)
async def test_project_template(
    template: Dict[str, str],
    run_cli: RunCLI,
) -> None:
    template_name, expected_command = template["name"], template["command"]
    command_result = await run_cli(["project", "template", template_name])
    assert expected_command in command_result.out, "Should show correct command"
