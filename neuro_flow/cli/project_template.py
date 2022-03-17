import click

from neuro_flow.cli.utils import wrap_async

from .root import Root


COOKIECUTTER_REPOS = {
    "recommended": "gh:neuro-inc/cookiecutter-neuro-project --checkout release",
    "barebone": "gh:neuro-inc/cookiecutter-neuro-project-barebone",
}

COOKIECUTTER_TEMPLATE = "cookiecutter {repo}"


@click.command()
@click.argument("template", type=click.Choice(["recommended", "barebone"]))
@wrap_async()
async def project_template(root: Root, template: str) -> None:
    """
    Provide instructions for the project template usage.
    """
    root.console.print(f"To use the {template} template, run the following command:")
    root.console.print(COOKIECUTTER_TEMPLATE.format(repo=COOKIECUTTER_REPOS[template]))
