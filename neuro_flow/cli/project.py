import click

from neuro_flow.cli.utils import wrap_async

from .root import Root


COOKIECUTTER_REPOS = {
    "recommended": "gh:neuro-inc/cookiecutter-neuro-project --branch release",
    "barebone": "gh:neuro-inc/cookiecutter-neuro-project-barebone",
}

COOKIECUTTER_TEMPLATE = "cookiecutter {repo}"


@click.group()
def project():
    """Output project template commands."""
    pass


@project.command()
@click.argument("template", type=click.Choice(["recommended", "barebone"]))
@wrap_async()
async def template(root: Root, template: str) -> None:
    """
    Provide instructions for the project template usage.
    """
    root.console.print(f"To use the {template} template, run the following command:")
    root.console.print(COOKIECUTTER_TEMPLATE.format(repo=COOKIECUTTER_REPOS[template]))
