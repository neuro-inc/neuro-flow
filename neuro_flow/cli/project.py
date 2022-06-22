import asyncio
import click
import importlib
import neuro_sdk
import shutil
import yaml
from contextlib import AsyncExitStack
from logging import getLogger
from pathlib import Path

from neuro_flow.cli.utils import wrap_async
from neuro_flow.storage.api import ApiStorage
from neuro_flow.storage.base import Storage

from .root import Root


logger = getLogger(__name__)

COOKIECUTTER_ARGS = {
    "recommended": {
        "cli": "gh:neuro-inc/cookiecutter-neuro-project --checkout release",
        "python": {
            "template": "gh:neuro-inc/cookiecutter-neuro-project",
            "checkout": "release",
        },
    },
    "barebone": {
        "cli": "gh:neuro-inc/cookiecutter-neuro-project-barebone",
        "python": {
            "template": "gh:neuro-inc/cookiecutter-neuro-project",
        },
    },
}

COOKIECUTTER_TEMPLATE = "cookiecutter {repo}"


@click.group()
def project() -> None:
    """Project-related commands"""
    pass


@click.command()
@click.argument("template", type=click.Choice(["recommended", "barebone"]))
@wrap_async()
async def template(root: Root, template: str) -> None:
    """
    Provide instructions for the project template usage.
    """
    root.console.print(f"To use the {template} template, run the following command:")
    root.console.print(f"cookiecutter {COOKIECUTTER_ARGS[template]['cli']}")


async def install_pip_package(package: str) -> None:
    python_executable = shutil.which("python3")
    logger.debug(f"Python executable: {python_executable}")
    prompt = f"Install {package} via pip? [Y/n]:"
    user_input = input(prompt)
    do_install = user_input.lower() in ("", "y")
    if not do_install:
        raise click.ClickException("Aborted")
    install_command = f"{python_executable} -m pip install {package}"
    logger.debug(f"Running '{install_command}'")
    subprocess = await asyncio.create_subprocess_shell(install_command)
    return_code = await subprocess.wait()
    if return_code != 0:
        raise click.ClickException(
            f"Command '{install_command}' exited with "
            f"non-zero status: {return_code}"
        )


# https://stackoverflow.com/a/24773951
async def install_if_missing(package: str) -> None:
    try:
        importlib.import_module(package)
    except ImportError:
        await install_pip_package(package=package)


async def create_project_from_template(template: str, storage: Storage) -> Path:
    from cookiecutter.main import cookiecutter  # type: ignore

    cookiecutter_args = COOKIECUTTER_ARGS[template]["python"]
    project_dir = Path(cookiecutter(**cookiecutter_args))
    yaml_file = project_dir / ".neuro" / "project.yml"
    yaml_contents = yaml.safe_load(yaml_file.read_text())
    yaml_id: str = yaml_contents["id"]
    try:
        project = await storage.create_project(yaml_id=yaml_id)
        # TODO: use rich to display results
        print(
            f"Created project {project.yaml_id} under organization {project.org_name} "
            f"in cluster {project.cluster} with owner {project.owner}"
        )
        return project_dir
    except neuro_sdk.IllegalArgumentError:
        raise click.ClickException(
            f"Cannot create project {yaml_id}: " "project with such name already exists"
        )


@click.command()
@click.argument("template", type=click.Choice(["recommended", "barebone"]))
@wrap_async()
async def init(root: Root, template: str) -> None:
    """Initialize a project from a selected template

    Creates required storage as well
    """
    # TODO: find better description
    await install_if_missing("cookiecutter")
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        await create_project_from_template(template=template, storage=storage)


project.add_command(template)
project.add_command(init)
