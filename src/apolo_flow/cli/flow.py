from dataclasses import dataclass

import asyncio
import click
from pathlib import Path
from typing import List, Optional

from apolo_flow.cli.utils import wrap_async

from .root import Root


@dataclass
class Spec:
    template: str
    checkout: Optional[str] = None


SPECS = {
    "barebone": Spec("gh:neuro-inc/cookiecutter-neuro-project"),
    "default": Spec("gh:neuro-inc/cookiecutter-neuro-project", checkout="release"),
}


def gen_cmd(spec: Spec, outdir: Path) -> List[str]:
    cmd = ["cookiecutter"]
    cmd.append(spec.template)
    if spec.checkout:
        cmd.append(f"--checkout")
        cmd.append(spec.checkout)
    cmd.append("--output-dir")
    cmd.append(str(outdir))
    return cmd


async def gen_project(root: Root, cmd: List[str]) -> None:
    root.console.print(f"[b]{cmd}[/b]")
    proc = await asyncio.create_subprocess_exec(*cmd)
    try:
        await proc.wait()
    except FileNotFoundError:
        root.console.print("Cannot find [b]cookiecutter[/b] executable")
        root.console.print(
            "Please run [i]pip install cookiecutter[/i] in your environment"
        )
        raise click.Abort()
    if proc.returncode:
        root.console.print(f"Failed with exitcode {proc.returncode}")
        raise click.Abort()


async def create_project_from_template(
    root: Root,
    template: str,
) -> None:
    outdir = Path.cwd()
    cmd = gen_cmd(SPECS[template], outdir)
    await gen_project(root, cmd)


@click.command()
@click.argument(
    "template",
    type=click.Choice(sorted(SPECS.keys())),
    default="default",
)
@wrap_async()
async def init(root: Root, template: str) -> None:
    """Initialize a flow from a selected template.

    Creates required storage as well.
    """
    await create_project_from_template(
        root,
        template=template,
    )
