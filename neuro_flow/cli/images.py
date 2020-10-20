import click

from neuro_flow.cli.click_types import LIVE_IMAGE_OR_ALL
from neuro_flow.cli.root import Root
from neuro_flow.cli.utils import argument, wrap_async
from neuro_flow.live_runner import LiveRunner


@click.command()
@argument("image", type=LIVE_IMAGE_OR_ALL)
@wrap_async()
async def build(root: Root, image: str) -> None:
    """Build an image.

    Assemble the IMAGE remotely and publish it.
    """
    async with LiveRunner(root.config_dir, root.console) as runner:
        if image == "ALL":
            await runner.build_all()
        else:
            await runner.build(image)
