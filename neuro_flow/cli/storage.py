import click
import neuro_sdk
import sys

from neuro_flow.cli.click_types import LIVE_VOLUME_OR_ALL
from neuro_flow.cli.root import Root
from neuro_flow.cli.utils import argument, wrap_async
from neuro_flow.live_runner import LiveRunner
from neuro_flow.storage import APIStorage, NeuroStorageFS, Storage


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack


@click.command()  # type: ignore
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
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        if volume != "ALL":
            await runner.upload(volume)
        else:
            await runner.upload_all()


@click.command()  # type: ignore
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
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        if volume != "ALL":
            await runner.download(volume)
        else:
            await runner.download_all()


@click.command()  # type: ignore
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
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        if volume != "ALL":
            await runner.clean(volume)
        else:
            await runner.clean_all()


@click.command()  # type: ignore
@wrap_async()
async def mkvolumes(
    root: Root,
) -> None:
    """Create all remote folders for volumes."""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(neuro_sdk.get())
        storage: Storage = await stack.enter_async_context(
            APIStorage(client, NeuroStorageFS(client))
        )
        runner = await stack.enter_async_context(
            LiveRunner(root.config_dir, root.console, client, storage, root)
        )
        await runner.mkvolumes()
