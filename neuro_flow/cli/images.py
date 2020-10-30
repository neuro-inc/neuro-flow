import click
import sys
from neuromation.api import get as api_get

from neuro_flow.cli.click_types import LIVE_IMAGE_OR_ALL
from neuro_flow.cli.root import Root
from neuro_flow.cli.utils import argument, wrap_async
from neuro_flow.live_runner import LiveRunner
from neuro_flow.storage import FSStorage, NeuroStorageFS, Storage


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack


@click.command()
@argument("image", type=LIVE_IMAGE_OR_ALL)
@wrap_async()
async def build(root: Root, image: str) -> None:
    """Build an image.

    Assemble the IMAGE remotely and publish it.
    """
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(api_get())
        storage: Storage = await stack.enter_async_context(
            FSStorage(NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage)
        )
        if image == "ALL":
            await runner.build_all()
        else:
            await runner.build(image)
