import click

from neuro_flow.cli.click_types import LIVE_VOLUME_OR_ALL
from neuro_flow.cli.utils import argument, wrap_async
from neuro_flow.live_runner import LiveRunner
from neuro_flow.parser import ConfigDir


@click.command()
@argument("volume", type=LIVE_VOLUME_OR_ALL)
@wrap_async()
async def upload(config_dir: ConfigDir, volume: str) -> None:
    """Upload volume.

    Upload local files to remote for VOLUME,
    use `upload ALL` for uploading all volumes."""
    async with LiveRunner(config_dir) as runner:
        if volume != "ALL":
            await runner.upload(volume)
        else:
            await runner.upload_all()


@click.command()
@argument("volume", type=LIVE_VOLUME_OR_ALL)
@wrap_async()
async def download(config_dir: ConfigDir, volume: str) -> None:
    """Download volume.

    Download remote files to local for VOLUME,
    use `download ALL` for downloading all volumes."""
    async with LiveRunner(config_dir) as runner:
        if volume != "ALL":
            await runner.download(volume)
        else:
            await runner.download_all()


@click.command()
@argument("volume", type=LIVE_VOLUME_OR_ALL)
@wrap_async()
async def clean(config_dir: ConfigDir, volume: str) -> None:
    """Clean volume.

    Clean remote files on VOLUME,
    use `clean ALL` for cleaning up all volumes."""
    async with LiveRunner(config_dir) as runner:
        if volume != "ALL":
            await runner.clean(volume)
        else:
            await runner.clean_all()


@click.command()
@wrap_async()
async def mkvolumes(config_dir: ConfigDir) -> None:
    """Create all remote folders for volumes."""
    async with LiveRunner(config_dir) as runner:
        await runner.mkvolumes()
