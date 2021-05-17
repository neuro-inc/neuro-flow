import abc
import click
import neuro_sdk
import operator
import sys
from neuro_cli.asyncio_utils import Runner
from typing import Callable, Generic, List, Optional, Sequence, Tuple, TypeVar, cast

from neuro_flow.batch_runner import BatchRunner
from neuro_flow.cli.root import Root
from neuro_flow.live_runner import LiveRunner
from neuro_flow.storage import APIStorage, NeuroStorageFS, Storage


if sys.version_info >= (3, 7):
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack

_T = TypeVar("_T")


class AsyncType(click.ParamType, Generic[_T], abc.ABC):  # type: ignore
    def convert(
        self,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> _T:
        assert ctx is not None
        root = cast(Root, ctx.obj)
        with Runner() as runner:
            return runner.run(self.async_convert(root, value, param, ctx))

    @abc.abstractmethod
    async def async_convert(
        self,
        root: Root,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> _T:
        pass

    def complete(
        self, ctx: click.Context, args: Sequence[str], incomplete: str  # type: ignore
    ) -> List[Tuple[str, Optional[str]]]:
        root = cast(Root, ctx.obj)
        with Runner() as runner:
            return runner.run(self.async_complete(root, ctx, args, incomplete))

    @abc.abstractmethod
    async def async_complete(
        self,
        root: Root,
        ctx: click.Context,  # type: ignore
        args: Sequence[str],
        incomplete: str,
    ) -> List[Tuple[str, Optional[str]]]:
        pass


class LiveJobType(AsyncType[str]):
    name = "job"

    def __init__(self, allow_all: bool = False):
        self._allow_all = allow_all

    async def async_convert(
        self,
        root: Root,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> str:
        return value

    async def async_complete(  # type: ignore[return]
        self,
        root: Root,
        ctx: click.Context,  # type: ignore
        args: Sequence[str],
        incomplete: str,
    ) -> List[Tuple[str, Optional[str]]]:
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(neuro_sdk.get())
            storage: Storage = await stack.enter_async_context(
                APIStorage(client, NeuroStorageFS(client))
            )
            runner = await stack.enter_async_context(
                LiveRunner(root.config_dir, root.console, client, storage, root)
            )
            variants = list(runner.flow.job_ids)
            if self._allow_all:
                variants += ["ALL"]
            return [
                (job_id, None) for job_id in variants if job_id.startswith(incomplete)
            ]


LIVE_JOB = LiveJobType(allow_all=False)
LIVE_JOB_OR_ALL = LiveJobType(allow_all=True)


class LiveJobSuffixType(AsyncType[str]):
    name = "suffix"

    def __init__(self, *, args_to_job_id: Callable[[Sequence[str]], str]):
        self._args_to_job_id = args_to_job_id

    async def async_convert(
        self,
        root: Root,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> str:
        return value

    async def async_complete(  # type: ignore[return]
        self,
        root: Root,
        ctx: click.Context,  # type: ignore
        args: Sequence[str],
        incomplete: str,
    ) -> List[Tuple[str, Optional[str]]]:
        job_id = self._args_to_job_id(args)
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(neuro_sdk.get())
            storage: Storage = await stack.enter_async_context(
                APIStorage(client, NeuroStorageFS(client))
            )
            runner = await stack.enter_async_context(
                LiveRunner(root.config_dir, root.console, client, storage, root)
            )
            return [
                (suffix, None)
                for suffix in await runner.list_suffixes(job_id)
                if suffix.startswith(incomplete)
            ]


SUFFIX_AFTER_LIVE_JOB = LiveJobSuffixType(args_to_job_id=operator.itemgetter(-1))


class LiveImageType(AsyncType[str]):
    name = "image"

    def __init__(self, allow_all: bool = False):
        self._allow_all = allow_all

    async def async_convert(
        self,
        root: Root,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> str:
        return value

    async def async_complete(  # type: ignore[return]
        self,
        root: Root,
        ctx: click.Context,  # type: ignore
        args: Sequence[str],
        incomplete: str,
    ) -> List[Tuple[str, Optional[str]]]:
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(neuro_sdk.get())
            storage: Storage = await stack.enter_async_context(
                APIStorage(client, NeuroStorageFS(client))
            )
            runner = await stack.enter_async_context(
                LiveRunner(root.config_dir, root.console, client, storage, root)
            )
            variants = [
                image
                for image, image_ctx in runner.flow.images.items()
                if image_ctx.context is not None
            ]
            if self._allow_all:
                variants += ["ALL"]
            return [(image, None) for image in variants if image.startswith(incomplete)]


LIVE_IMAGE_OR_ALL = LiveImageType(allow_all=True)


class LiveVolumeType(AsyncType[str]):
    name = "volume"

    def __init__(self, allow_all: bool = False):
        self._allow_all = allow_all

    async def async_convert(
        self,
        root: Root,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> str:
        return value

    async def async_complete(  # type: ignore[return]
        self,
        root: Root,
        ctx: click.Context,  # type: ignore
        args: Sequence[str],
        incomplete: str,
    ) -> List[Tuple[str, Optional[str]]]:
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(neuro_sdk.get())
            storage: Storage = await stack.enter_async_context(
                APIStorage(client, NeuroStorageFS(client))
            )
            runner = await stack.enter_async_context(
                LiveRunner(root.config_dir, root.console, client, storage, root)
            )
            variants = [
                volume.id
                for volume in runner.flow.volumes.values()
                if volume.local is not None
            ]
            if self._allow_all:
                variants += ["ALL"]
            return [(image, None) for image in variants if image.startswith(incomplete)]


LIVE_VOLUME_OR_ALL = LiveVolumeType(allow_all=True)


class BatchType(AsyncType[str]):
    name = "batch"

    def __init__(self, allow_all: bool = False):
        self._allow_all = allow_all

    async def async_convert(
        self,
        root: Root,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> str:
        return value

    async def async_complete(
        self,
        root: Root,
        ctx: click.Context,  # type: ignore
        args: Sequence[str],
        incomplete: str,
    ) -> List[Tuple[str, Optional[str]]]:
        variants = []
        for file in root.config_dir.config_dir.rglob("*.yml"):
            # We are not trying to parse properly to allow autocompletion of
            # broken yaml files
            if "batch" in file.read_text():
                variants.append(file.stem)
        if self._allow_all:
            variants += ["ALL"]
        return [(batch, None) for batch in variants if batch.startswith(incomplete)]


BATCH = BatchType(allow_all=False)
BATCH_OR_ALL = BatchType(allow_all=True)


class BakeType(AsyncType[str]):
    name = "bake"

    async def async_convert(
        self,
        root: Root,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> str:
        return value

    async def async_complete(
        self,
        root: Root,
        ctx: click.Context,  # type: ignore
        args: Sequence[str],
        incomplete: str,
    ) -> List[Tuple[str, Optional[str]]]:
        variants = []
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(neuro_sdk.get())
            storage: Storage = await stack.enter_async_context(
                APIStorage(client, NeuroStorageFS(client))
            )
            runner: BatchRunner = await stack.enter_async_context(
                BatchRunner(root.config_dir, root.console, client, storage, root)
            )
            try:
                async for bake in runner.get_bakes():
                    variants.append(bake.bake_id)
                    if bake.name is not None:
                        variants.append(bake.name)
            except ValueError:
                pass
        return [(bake, None) for bake in variants if bake.startswith(incomplete)]


BAKE = BakeType()


class BakeTaskType(AsyncType[str]):
    name = "task"

    def __init__(
        self,
        *,
        args_to_bake_id: Callable[[Sequence[str]], str],
        args_to_attempt: Callable[[Sequence[str]], int],
        include_started: bool = True,
        include_finished: bool = True,
    ):
        self._args_to_bake_id = args_to_bake_id
        self._args_to_attempt = args_to_attempt
        self._include_started = include_started
        self._include_finished = include_finished

    async def async_convert(
        self,
        root: Root,
        value: str,
        param: Optional[click.Parameter],  # type: ignore
        ctx: Optional[click.Context],  # type: ignore
    ) -> str:
        return value

    async def async_complete(
        self,
        root: Root,
        ctx: click.Context,  # type: ignore
        args: Sequence[str],
        incomplete: str,
    ) -> List[Tuple[str, Optional[str]]]:
        variants: List[str] = []
        bake_id = self._args_to_bake_id(args)
        attempt_no = self._args_to_attempt(args)
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(neuro_sdk.get())
            storage: Storage = await stack.enter_async_context(
                APIStorage(client, NeuroStorageFS(client))
            )
            runner: BatchRunner = await stack.enter_async_context(
                BatchRunner(root.config_dir, root.console, client, storage, root)
            )
            attempt = await runner.get_bake_attempt(bake_id, attempt_no=attempt_no)
            started, finished = await storage.fetch_attempt(attempt)
            if self._include_finished:
                variants.extend(".".join(parts) for parts in finished.keys())
            if self._include_started:
                variants.extend(
                    ".".join(parts) for parts in started.keys() if parts not in finished
                )
        return [(task, None) for task in variants if task.startswith(incomplete)]


def extract_attempt_no(args: Sequence[str]) -> int:
    for index, arg in enumerate(args):
        if arg == "-a" or arg == "--attempt":
            try:
                return int(args[index + 1])
            except (ValueError, IndexError):
                pass
    return -1


FINISHED_TASK_AFTER_BAKE = BakeTaskType(
    include_started=False,
    include_finished=True,
    args_to_bake_id=operator.itemgetter(-1),
    args_to_attempt=extract_attempt_no,
)
