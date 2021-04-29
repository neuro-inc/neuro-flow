import dataclasses

import abc
import aiohttp
import secrets
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
    Awaitable,
    BinaryIO,
    Callable,
    Dict,
    Mapping,
    Optional,
    Sequence,
    TextIO,
    Tuple,
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
from neuro_flow.types import LocalPath


if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


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
        for ext in (".yml", ".yaml"):
            path = self._workspace / "project"
            path = path.with_suffix(ext)
            if path.exists():
                with path.open() as f:
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
        scheme, sep, spec = action_name.partition(":")
        if not sep:
            raise ValueError(f"{action_name} has no schema")
        if scheme in ("ws", "workspace"):
            path = self._workspace / spec
            if not path.exists():
                path = path.with_suffix(".yml")
            if not path.exists():
                path = path.with_suffix(".yaml")
            if not path.exists():
                raise ValueError(f"Action {action_name} does not exist")
            with path.open() as f:
                yield f
        elif scheme in ("gh", "github"):
            repo, sep, version = spec.partition("@")
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
                            yield TextIOWrapper(cast(BinaryIO, file_obj))
        else:
            raise ValueError(f"Unsupported scheme '{scheme}'")

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
        self, name: str
    ) -> Tuple[Mapping[str, Any], Sequence["ConfigFile"]]:
        async with self.project_stream() as stream:
            proj_conf: Optional[ConfigFile]
            if stream is not None:
                proj_conf, proj_conf_meta = self._stream_to_config(stream)
            else:
                proj_conf = None
        async with self.flow_stream(name) as stream:
            flow_conf, flow_conf_meta = self._stream_to_config(stream)

        flow_ast = await self.fetch_flow(name)
        actions: Dict[str, Tuple["ConfigFile", "ConfigOnStorage"]] = {}
        await self._collect_actions(flow_ast.tasks, actions)
        meta = ConfigsMeta(
            workspace=self.workspace,
            project_config=proj_conf_meta if proj_conf else None,
            flow_config=flow_conf_meta,
            action_configs={
                key: action_conf_meta for key, (_, action_conf_meta) in actions.items()
            },
        )
        configs = [flow_conf, *(action_conf for action_conf, _ in actions.values())]
        if proj_conf:
            configs.append(proj_conf)
        return meta.to_json(), configs

    def _stream_to_config(
        self, stream: TextIO
    ) -> Tuple["ConfigFile", "ConfigOnStorage"]:
        config_file = ConfigFile(
            filename=secrets.token_hex(16),  # Use random filenames
            content=stream.read(),
        )
        config_on_storage = ConfigOnStorage(
            storage_filename=config_file.filename,
            real_name=stream.name,
        )
        return config_file, config_on_storage

    async def _collect_actions(
        self,
        tasks: Sequence[Union[ast.Task, ast.TaskActionCall]],
        collect_to: Dict[str, Tuple["ConfigFile", "ConfigOnStorage"]],
    ) -> None:
        from neuro_flow.context import EMPTY_ROOT

        # Local import here to avoid circular imports
        # In general, config loader should not use
        # contexts, but collecting actions requires eval()
        # for action names.

        for task in tasks:
            if isinstance(task, ast.BaseActionCall):
                action_name = await task.action.eval(EMPTY_ROOT)
                if action_name in collect_to:
                    continue
                async with self.action_stream(action_name) as stream:
                    collect_to[action_name] = self._stream_to_config(stream)
                action_ast = await self.fetch_action(action_name)
                if isinstance(action_ast, ast.BatchAction):
                    await self._collect_actions(action_ast.tasks, collect_to)


@dataclasses.dataclass(frozen=True)
class ConfigFile:
    filename: str
    content: str


@dataclasses.dataclass(frozen=True)
class ConfigOnStorage:
    storage_filename: str
    real_name: str

    def to_json(self) -> Mapping[str, Any]:
        return {
            "storage_filename": self.storage_filename,
            "real_name": self.real_name,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ConfigOnStorage":
        return cls(
            storage_filename=data["storage_filename"],
            real_name=data["real_name"],
        )


@dataclasses.dataclass(frozen=True)
class ConfigsMeta:
    workspace: LocalPath
    flow_config: ConfigOnStorage
    project_config: Optional[ConfigOnStorage]
    action_configs: Mapping[str, ConfigOnStorage]

    def to_json(self) -> Mapping[str, Any]:
        return {
            "workspace": str(self.workspace),
            "flow_config": self.flow_config.to_json(),
            "project_config": self.project_config.to_json()
            if self.project_config
            else None,
            "action_configs": {
                key: config.to_json() for key, config in self.action_configs.items()
            },
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ConfigsMeta":
        if data.get("project_config"):
            project_config: Optional[ConfigOnStorage] = ConfigOnStorage.from_json(
                data["project_config"]
            )
        else:
            project_config = None
        return cls(
            workspace=LocalPath(data["workspace"]),
            flow_config=ConfigOnStorage.from_json(data["flow_config"]),
            project_config=project_config,
            action_configs={
                key: ConfigOnStorage.from_json(config)
                for key, config in data["action_configs"].items()
            },
        )


class NamedStringIO(StringIO):
    name: str = "<stringio>"  # To override property

    def __init__(self, content: str, name: str):
        super().__init__(content)
        self.name = name


class BatchRemoteCL(BatchStreamCL):
    def __init__(
        self,
        meta: Mapping[str, Any],
        load_from_storage: Callable[[str], Awaitable[str]],
        client: Client,
    ):
        super().__init__()
        self._meta = ConfigsMeta.from_json(meta)
        self._load_from_storage = load_from_storage
        self._client = client

    @property
    def client(self) -> Client:
        return self._client

    @property
    def workspace(self) -> LocalPath:
        return self._meta.workspace

    async def _fetch_config(self, config: ConfigOnStorage) -> TextIO:
        content = await self._load_from_storage(config.storage_filename)
        return NamedStringIO(content=content, name=config.real_name)

    @asynccontextmanager
    async def flow_stream(self, name: str) -> AsyncIterator[TextIO]:
        yield await self._fetch_config(self._meta.flow_config)

    @asynccontextmanager
    async def project_stream(self) -> AsyncIterator[Optional[TextIO]]:
        if self._meta.project_config:
            yield await self._fetch_config(self._meta.project_config)
        else:
            yield None

    @asynccontextmanager
    async def action_stream(self, action_name: str) -> AsyncIterator[TextIO]:
        yield await self._fetch_config(self._meta.action_configs[action_name])
