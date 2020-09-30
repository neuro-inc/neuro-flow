import click
import logging
from typing import Any, List, Optional

from neuro_flow.cli import batch, completion, images, live, storage
from neuro_flow.parser import ConfigDir, find_workspace
from neuro_flow.types import LocalPath


class MainGroup(click.Group):
    def _process_args(
        self, ctx: click.Context, config: Optional[str], fake_workspace: bool
    ) -> None:
        logging.basicConfig(level=logging.INFO)
        if fake_workspace:
            config_dir = ConfigDir(
                LocalPath("running-with-fake-workspace"),
                LocalPath("running-with-fake-workspace"),
            )
        else:
            config_dir = find_workspace(config)
        ctx.obj = config_dir

    def make_context(
        self,
        info_name: str,
        args: List[str],
        parent: Optional[click.Context] = None,
        **extra: Any,
    ) -> click.Context:
        ctx = super().make_context(info_name, args, parent, **extra)
        kwargs = {}
        for param in self.params:
            if param.expose_value:
                val = ctx.params.get(param.name)
                if val is not None:
                    kwargs[param.name] = val
                else:
                    kwargs[param.name] = param.get_default(ctx)

        self._process_args(ctx, **kwargs)

        return ctx


@click.group(cls=MainGroup)
@click.option(
    "--config",
    type=click.Path(dir_okay=True, file_okay=False),
    required=False,
    help=(
        "Path to a directory with .neuro folder inside, "
        "automatic lookup is performed if not set (default)"
    ),
    default=None,
    metavar="PATH",
)
@click.option(
    "--fake-workspace",
    hidden=True,
    is_flag=True,
    default=False,
    required=False,
)
def main(config: Optional[str], fake_workspace: bool) -> None:
    pass  # parameters processed in MainGroup._process_args


# Live commands
main.add_command(live.run)
main.add_command(live.ps)
main.add_command(live.logs)
main.add_command(live.status)
main.add_command(live.kill)

# Batch commands
main.add_command(batch.bake)
main.add_command(batch.execute)
main.add_command(batch.bakes)
main.add_command(batch.show)
main.add_command(batch.inspect)
main.add_command(batch.cancel)
main.add_command(batch.clear_cache)

# Volumes commands
main.add_command(storage.upload)
main.add_command(storage.download)
main.add_command(storage.clean)
main.add_command(storage.mkvolumes)

# Image commands
main.add_command(images.build)

# Completion commands
main.add_command(completion.completion)
