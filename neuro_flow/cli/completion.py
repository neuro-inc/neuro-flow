import click
import os
import sys

from neuro_flow.cli.utils import wrap_async
from neuro_flow.types import LocalPath


CFG_FILE = {"bash": LocalPath("~/.bashrc"), "zsh": LocalPath("~/.zshrc")}
SOURCE_CMD = {"bash": "source", "zsh": "source_zsh"}

ACTIVATION_TEMPLATE = 'eval "$(_NEURO_FLOW_COMPLETE={cmd} {exe})"'


@click.group()
def completion() -> None:
    """
    Output shell completion code.
    """


@completion.command()
@click.argument("shell", type=click.Choice(["bash", "zsh"]))
@wrap_async(pass_obj=False)
async def generate(shell: str) -> None:
    """
    Provide an instruction for shell completion generation.
    """
    click.echo(f"Push the following line into your {CFG_FILE[shell]}")
    click.echo(ACTIVATION_TEMPLATE.format(cmd=SOURCE_CMD[shell], exe=sys.argv[0]))


@completion.command()
@click.argument("shell", type=click.Choice(["bash", "zsh"]))
@wrap_async(pass_obj=False)
async def patch(shell: str) -> None:
    """
    Automatically patch shell configuration profile to enable completion
    """
    profile_file = CFG_FILE[shell].expanduser()
    with profile_file.open("ab+") as profile:
        profile.write(
            b"\n"
            + os.fsencode(
                ACTIVATION_TEMPLATE.format(cmd=SOURCE_CMD[shell], exe=sys.argv[0])
            )
            + b"\n"
        )
