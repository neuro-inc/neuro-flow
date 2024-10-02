import apolo_sdk
import click
from contextlib import AsyncExitStack

from apolo_flow.cli.click_types import LIVE_VOLUME_OR_ALL
from apolo_flow.cli.root import Root
from apolo_flow.cli.utils import argument, wrap_async
from apolo_flow.live_runner import LiveRunner
from apolo_flow.storage.api import ApiStorage
from apolo_flow.storage.base import Storage


@click.command()
@argument("volume", type=LIVE_VOLUME_OR_ALL)
@wrap_async()
async def upload(
    root: Root,
    volume: str,
) -> None:
    """Upload volume.

    Upload local files to remote for VOLUME,
    use `upload ALL` for uploading all volumes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(apolo_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        if volume != "ALL":
            await runner.upload(volume)
        else:
            await runner.upload_all()


@click.command()
@argument("volume", type=LIVE_VOLUME_OR_ALL)
@wrap_async()
async def download(
    root: Root,
    volume: str,
) -> None:
    """Download volume.

    Download remote files to local for VOLUME,
    use `download ALL` for downloading all volumes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(apolo_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        if volume != "ALL":
            await runner.download(volume)
        else:
            await runner.download_all()


@click.command()
@argument("volume", type=LIVE_VOLUME_OR_ALL)
@wrap_async()
async def clean(
    root: Root,
    volume: str,
) -> None:
    """Clean volume.

    Clean remote files on VOLUME,
    use `clean ALL` for cleaning up all volumes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(apolo_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        if volume != "ALL":
            await runner.clean(volume)
        else:
            await runner.clean_all()


@click.command()
@wrap_async()
async def mkvolumes(
    root: Root,
) -> None:
    """Create all remote folders for volumes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(apolo_sdk.get())
        storage: Storage = await stack.enter_async_context(ApiStorage(client))
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        await runner.mkvolumes()
