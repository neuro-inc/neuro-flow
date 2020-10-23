import click
import logging
import sys
from click.exceptions import Abort as ClickAbort, Exit as ClickExit
from neuromation.cli.log_formatter import ConsoleHandler
from rich.console import Console
from typing import Any, List, Optional

from neuro_flow.cli import batch, completion, images, live, storage
from neuro_flow.parser import ConfigDir, find_workspace
from neuro_flow.types import LocalPath

from .root import Root


log = logging.getLogger(__name__)


LOG_ERROR = log.error


def setup_logging(verbosity: int) -> None:
    root_logger = logging.getLogger()
    handler = ConsoleHandler()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG)

    if verbosity <= 1:
        formatter = logging.Formatter()
    else:
        formatter = logging.Formatter("%(name)s.%(funcName)s: %(message)s")

    if verbosity < -1:
        loglevel = logging.CRITICAL
    elif verbosity == -1:
        loglevel = logging.ERROR
    elif verbosity == 0:
        loglevel = logging.WARNING
    elif verbosity == 1:
        loglevel = logging.INFO
    else:
        loglevel = logging.DEBUG

    handler.setFormatter(formatter)
    handler.setLevel(loglevel)


class MainGroup(click.Group):
    def _process_args(
        self,
        ctx: click.Context,
        config: Optional[str],
        fake_workspace: bool,
        verbose: int,
        quiet: int,
        show_traceback: bool,
    ) -> None:
        if fake_workspace:
            config_dir = ConfigDir(
                LocalPath("running-with-fake-workspace"),
                LocalPath("running-with-fake-workspace"),
            )
        else:
            config_dir = find_workspace(config)

        setup_logging(verbosity=verbose - quiet)

        global LOG_ERROR
        if show_traceback:
            LOG_ERROR = log.exception

        ctx.obj = Root(config_dir=config_dir, console=Console(highlight=False))

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
    "-v",
    "--verbose",
    count=True,
    type=int,
    default=0,
    help="Give more output. Option is additive, and can be used up to 2 times.",
)
@click.option(
    "-q",
    "--quiet",
    count=True,
    type=int,
    default=0,
    help="Give less output. Option is additive, and can be used up to 2 times.",
)
@click.option(
    "--show-traceback",
    is_flag=True,
    help="Show python traceback on error, useful for debugging the tool.",
)
@click.option(
    "--fake-workspace",
    hidden=True,
    is_flag=True,
    default=False,
    required=False,
)
def cli(
    config: Optional[str],
    fake_workspace: bool,
    verbose: int,
    quiet: int,
    show_traceback: bool,
) -> None:
    pass  # parameters processed in MainGroup._process_args


# Live commands
cli.add_command(live.run)
cli.add_command(live.ps)
cli.add_command(live.logs)
cli.add_command(live.status)
cli.add_command(live.kill)

# Batch commands
cli.add_command(batch.bake)
cli.add_command(batch.execute)
cli.add_command(batch.bakes)
cli.add_command(batch.show)
cli.add_command(batch.inspect)
cli.add_command(batch.cancel)
cli.add_command(batch.clear_cache)
cli.add_command(batch.restart)

# Volumes commands
cli.add_command(storage.upload)
cli.add_command(storage.download)
cli.add_command(storage.clean)
cli.add_command(storage.mkvolumes)

# Image commands
cli.add_command(images.build)

# Completion commands
cli.add_command(completion.completion)


def main(args: Optional[List[str]] = None) -> None:
    try:
        cli.main(args=args, standalone_mode=False)
    except ClickAbort:
        LOG_ERROR("Aborting.")
        sys.exit(130)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except ClickExit as e:
        sys.exit(e.exit_code)  # type: ignore

    except SystemExit:
        raise

    except Exception as e:
        LOG_ERROR(f"{e}")
        sys.exit(1)
