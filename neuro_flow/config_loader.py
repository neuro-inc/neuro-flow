import dataclasses

import abc
import aiohttp
import logging
import sys
import tarfile
from aiohttp.web_exceptions import HTTPNotFound
from io import StringIO, TextIOWrapper
from neuro_sdk import Client
from pathlib import PureWindowsPath
from tempfile import TemporaryFile
from typing import (
    IO,
    Any,
    AsyncIterator,
    BinaryIO,
    Dict,
    Optional,
    Sequence,
    TextIO,
    Union,
    cast,
)

from neuro_flow import ast
from neuro_flow.parser import (
    ConfigDir,
    make_default_project,
    parse_action_stream,
    parse_batch_stream,
    parse_live_stream,
    parse_project_stream,
)
from neuro_flow.storage.base import BakeStorage, ConfigsMeta
from neuro_flow.types import LocalPath


if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ActionSpec:
    scheme: str
    spec: str

    @property
    def is_local(self) -> bool:
        return self.scheme in ("ws", "workspace")

    @property
    def is_github(self) -> bool:
        return self.scheme in ("gh", "github")

    @classmethod
    def parse(cls, action_name: str) -> "ActionSpec":
        scheme, sep, spec = action_name.partition(":")
        if not sep:
            raise ValueError(f"{action_name} has no schema")
        return ActionSpec(scheme, spec)


class ConfigLoader(abc.ABC):
    @property
    @abc.abstractmethod
    def workspace(self) -> LocalPath:
        pass

    @abc.abstractmethod
    async def fetch_flow(self, name: str) -> ast.BaseFlow:
        pass

    @abc.abstractmethod
    async def fetch_project(self) -> ast.Project:
        pass

    @abc.abstractmethod
    async def fetch_action(self, action_name: str) -> ast.BaseAction:
        pass

    @property
    @abc.abstractmethod
    def client(self) -> Client:
        pass


class StreamCL(ConfigLoader, abc.ABC):
    __project_cache: Optional[ast.Project]
    __action_cache: Dict[str, ast.BaseAction]

    def __init__(self) -> None:
        self.__project_cache = None
        self.__action_cache = dict()

    @asynccontextmanager
    @abc.abstractmethod
    async def project_stream(self) -> AsyncIterator[Optional[TextIO]]:
        yield None

    @asynccontextmanager
    @abc.abstractmethod
    async def action_stream(self, action_name: str) -> AsyncIterator[TextIO]:
        # Yield for type check only in asynccontextmanager
        yield None  # type: ignore

    async def _fetch_project(self) -> ast.Project:
        async with self.project_stream() as stream:
            if stream is not None:
                return parse_project_stream(stream)
            # Tmp hack to overcome windows path issue.
            try:
                workspace_as_windows = PureWindowsPath(str(self.workspace))
            except ValueError:
                return make_default_project(self.workspace.stem)
            else:
                return make_default_project(workspace_as_windows.stem)

    async def fetch_project(self) -> ast.Project:
        if not self.__project_cache:
            self.__project_cache = await self._fetch_project()
        return self.__project_cache

    async def _fetch_action(self, action_name: str) -> ast.BaseAction:
        async with self.action_stream(action_name) as stream:
            return parse_action_stream(stream)

    async def fetch_action(self, action_name: str) -> ast.BaseAction:
        if action_name not in self.__action_cache:
            self.__action_cache[action_name] = await self._fetch_action(action_name)
        return self.__action_cache[action_name]


class LiveStreamCL(StreamCL, abc.ABC):
    __flow_cache: Dict[str, ast.LiveFlow]

    def __init__(self) -> None:
        super().__init__()
        self.__flow_cache = dict()

    @asynccontextmanager
    @abc.abstractmethod
    async def flow_stream(self, name: str) -> AsyncIterator[TextIO]:
        # Yield for type check only in asynccontextmanager
        yield None  # type: ignore

    async def _fetch_flow(self, name: str) -> ast.LiveFlow:
        async with self.flow_stream(name) as stream:
            return parse_live_stream(stream)

    async def fetch_flow(self, name: str) -> ast.LiveFlow:
        if name not in self.__flow_cache:
            self.__flow_cache[name] = await self._fetch_flow(name)
        return self.__flow_cache[name]


class BatchStreamCL(StreamCL, abc.ABC):
    __flow_cache: Dict[str, ast.BatchFlow]

    def __init__(self) -> None:
        super().__init__()
        self.__flow_cache = dict()

    @asynccontextmanager
    @abc.abstractmethod
    async def flow_stream(self, name: str) -> AsyncIterator[TextIO]:
        # Yield for type check only in asynccontextmanager
        yield None  # type: ignore

    async def _fetch_flow(self, name: str) -> ast.BatchFlow:
        async with self.flow_stream(name) as stream:
            return parse_batch_stream(stream)

    async def fetch_flow(self, name: str) -> ast.BatchFlow:
        if name not in self.__flow_cache:
            self.__flow_cache[name] = await self._fetch_flow(name)
        return self.__flow_cache[name]


class NamedTextIOWrapper(TextIOWrapper):
    name: str = "<textiowrapper>"  # To override the property

    def __init__(self, name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.name = name


class LocalCL(StreamCL, abc.ABC):
    def __init__(self, config_dir: ConfigDir, client: Client):
        super().__init__()
        self._workspace = config_dir.workspace.resolve()
        self._config_dir = config_dir.config_dir.resolve()
        self._github_session = aiohttp.ClientSession()
        self._client = client

    async def close(self) -> None:
        await self._github_session.close()

    @property
    def client(self) -> Client:
        return self._client

    @property
    def workspace(self) -> LocalPath:
        return self._workspace

    @asynccontextmanager
    async def project_stream(self) -> AsyncIterator[Optional[TextIO]]:
        for dir in (self._config_dir, self._workspace):
            for ext in (".yml", ".yaml"):
                path = dir / "project"
                path = path.with_suffix(ext)
                if path.exists():
                    with path.open() as f:
                        if dir == self._workspace:
                            log.warning(
                                f"Using project yaml file from workspace instead"
                                f" of config directory {self._config_dir}. Please move "
                                "it there, reading from workspace will be removed soon."
                            )
                        yield f
                        return
        yield None

    def flow_path(self, name: str) -> LocalPath:
        for ext in (".yml", ".yaml"):
            ret = self._config_dir / name
            ret = ret.with_suffix(ext).resolve()
            if ret.exists():
                if not ret.is_file():
                    raise ValueError(f"Flow {ret} is not a file")
                return ret
        raise ValueError(
            f"Config file for flow '{name}' not found " f"in {self._config_dir} folder"
        )

    @asynccontextmanager
    async def flow_stream(self, name: str) -> AsyncIterator[TextIO]:
        with self.flow_path(name).open() as f:
            yield f

    @asynccontextmanager
    async def action_stream(self, action_name: str) -> AsyncIterator[TextIO]:
        action = ActionSpec.parse(action_name)
        if action.is_local:
            path = self._workspace / action.spec
            if not path.exists():
                path = path.with_suffix(".yml")
            if not path.exists():
                path = path.with_suffix(".yaml")
            if not path.exists():
                raise ValueError(f"Action {action_name} does not exist")
            with path.open() as f:
                yield f
        elif action.is_github:
            repo, sep, version = action.spec.partition("@")
            if not sep:
                raise ValueError(f"{action_name} is github action, but has no version")
            async with self._tarball_from_github(repo, version) as tarball:
                tar = tarfile.open(fileobj=tarball)
                for member in tar.getmembers():
                    member_path = LocalPath(member.name)
                    # find action yml file
                    if len(member_path.parts) == 2 and (
                        member_path.parts[1] == "action.yml"
                        or member_path.parts[1] == "action.yaml"
                    ):
                        if member.isfile():
                            file_obj = tar.extractfile(member)
                            if file_obj is None:
                                raise ValueError(
                                    f"Github repo {repo} do not contain "
                                    '"action.yml" or "action.yaml" files.'
                                )
                            # Cast is workaround for
                            # https://github.com/python/typeshed/issues/4349
                            yield NamedTextIOWrapper(
                                action_name, cast(BinaryIO, file_obj)
                            )
        else:
            raise ValueError(f"Unsupported scheme '{action.scheme}'")

    @asynccontextmanager
    async def _tarball_from_github(
        self, repo: str, version: str
    ) -> AsyncIterator[IO[bytes]]:
        with TemporaryFile() as file:
            assert self._github_session, "LocalCL was not initialised properly"
            async with self._github_session.get(
                url=f"https://api.github.com/repos/{repo}/tarball/{version}"
            ) as response:
                if response.status == HTTPNotFound.status_code:
                    raise ValueError(
                        "Cannot fetch action: "
                        f"either repository '{repo}' or tag '{version}' does not exist"
                    )
                response.raise_for_status()
                async for chunk in response.content:
                    file.write(chunk)
            file.seek(0)
            yield file


class LiveLocalCL(LocalCL, LiveStreamCL):
    pass


class BatchLocalCL(
    LocalCL,
    BatchStreamCL,
):
    async def collect_configs(
        self, name: str, bake_storage: BakeStorage
    ) -> ConfigsMeta:
        async with self.project_stream() as stream:
            proj_conf_id: Optional[str]
            if stream is not None:
                proj_conf_id = await self._upload_config(stream, bake_storage)
            else:
                proj_conf_id = None
        async with self.flow_stream(name) as stream:
            flow_conf_id = await self._upload_config(stream, bake_storage)

        flow_ast = await self.fetch_flow(name)
        actions: Dict[str, str] = {}
        await self._collect_actions(flow_ast.tasks, actions, bake_storage)
        meta = ConfigsMeta(
            workspace=str(self.workspace),
            project_config_id=proj_conf_id,
            flow_config_id=flow_conf_id,
            action_config_ids=actions,
        )
        return meta

    async def _upload_config(self, stream: TextIO, bake_storage: BakeStorage) -> str:
        config = await bake_storage.create_config_file(
            filename=stream.name,
            content=stream.read(),
        )
        return config.id

    async def _collect_actions(
        self,
        tasks: Sequence[Union[ast.Task, ast.TaskActionCall, ast.TaskModuleCall]],
        collect_to: Dict[str, str],
        bake_storage: BakeStorage,
    ) -> None:
        from neuro_flow.context import EMPTY_ROOT

        # Local import here to avoid circular imports
        # In general, config loader should not use
        # contexts, but collecting actions requires eval()
        # for action names.

        for task in tasks:
            if isinstance(task, ast.BaseActionCall):
                action_name = await task.action.eval(EMPTY_ROOT)
            elif isinstance(task, ast.BaseModuleCall):
                action_name = await task.module.eval(EMPTY_ROOT)
            else:
                continue
            if action_name in collect_to:
                continue
            async with self.action_stream(action_name) as stream:
                collect_to[action_name] = await self._upload_config(
                    stream, bake_storage
                )
            action_ast = await self.fetch_action(action_name)
            if isinstance(action_ast, ast.BatchAction):
                await self._collect_actions(action_ast.tasks, collect_to, bake_storage)


class NamedStringIO(StringIO):
    name: str = "<stringio>"  # To override property

    def __init__(self, content: str, name: str):
        super().__init__(content)
        self.name = name


class BatchRemoteCL(BatchStreamCL):
    def __init__(
        self,
        meta: ConfigsMeta,
        client: Client,
        bake_storage: BakeStorage,
    ):
        super().__init__()
        self._meta = meta
        self._client = client
        self._bake_storage = bake_storage

    @property
    def client(self) -> Client:
        return self._client

    @property
    def workspace(self) -> LocalPath:
        return LocalPath(self._meta.workspace)

    async def _to_stream(self, config_id: str) -> TextIO:
        config = await self._bake_storage.config_file(id=config_id).get()
        return NamedStringIO(content=config.content, name=config.filename)

    @asynccontextmanager
    async def flow_stream(self, name: str) -> AsyncIterator[TextIO]:
        yield await self._to_stream(self._meta.flow_config_id)

    @asynccontextmanager
    async def project_stream(self) -> AsyncIterator[Optional[TextIO]]:
        if self._meta.project_config_id:
            yield await self._to_stream(self._meta.project_config_id)
        else:
            yield None

    @asynccontextmanager
    async def action_stream(self, action_name: str) -> AsyncIterator[TextIO]:
        yield await self._to_stream(self._meta.action_config_ids[action_name])
