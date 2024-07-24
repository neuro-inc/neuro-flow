import dataclasses

import abc
import asyncio
import logging
from apolo_sdk import Client
from contextlib import asynccontextmanager, suppress
from io import StringIO, TextIOWrapper
from pathlib import PureWindowsPath
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from typing import Any, AsyncIterator, Dict, Optional, Sequence, TextIO, Union

from apolo_flow import ast
from apolo_flow.parser import (
    ConfigDir,
    make_default_project,
    parse_action_stream,
    parse_batch_stream,
    parse_live_stream,
    parse_project_stream,
)
from apolo_flow.storage.base import BakeStorage, ConfigsMeta
from apolo_flow.types import LocalPath


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
        self._tempdir: Optional["TemporaryDirectory[str]"] = None
        self._client = client

    async def close(self) -> None:
        if self._tempdir is not None:
            # Nothing to do if cleanup fails for some reason
            with suppress(OSError):
                self._tempdir.cleanup()

    def _get_tempdir(self) -> LocalPath:
        if self._tempdir is None:
            self._tempdir = TemporaryDirectory(suffix="github-flow")
        return LocalPath(self._tempdir.name)

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
        EXTS = (".yml", ".yaml")
        action = ActionSpec.parse(action_name)
        if action.is_github:
            target_dir = await self._clone_github_repo(action.spec)
            for ext in EXTS:
                path = target_dir / ("action" + ext)
                if path.exists():
                    break
            else:
                raise ValueError(
                    f"Github repo {action.spec} shold contain "
                    "either ./action.yml or ./action.yaml file."
                )
            with path.open() as f:
                yield f
        elif action.is_local:
            for ext in ("",) + EXTS:
                path = self._workspace / (action.spec + ext)
                if path.exists():
                    break
            else:
                raise ValueError(f"Action {action_name} does not exist")
            with path.open() as f:
                yield f
        else:
            raise ValueError(f"Unsupported scheme '{action.scheme}'")

    async def _clone_github_repo(self, action_spec: str) -> LocalPath:
        spec, sep, version = action_spec.partition("@")
        err_text = f"{action_spec} should have {{OWNER}}/{{REPO}}@{{VERSION}} format"
        if not sep:
            raise ValueError(err_text)
        tempdir = self._get_tempdir()
        repo_spec = f"git@github.com:{spec}.git"
        owner, sep, repo = spec.partition("/")
        if not sep:
            raise ValueError(err_text)
        target_dir = tempdir / repo
        idx = 0
        while target_dir.exists():
            target_dir = tempdir / (repo + f"_{idx}")
            idx += 1
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--branch",
            version,
            "--depth",
            "1",
            "--config",
            "advice.detachedHead=false",
            repo_spec,
            str(target_dir),
            cwd=str(tempdir),
        )
        retcode = await proc.wait()
        if retcode:
            raise CalledProcessError(retcode, "git")
        return target_dir


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
        from apolo_flow.context import EMPTY_ROOT

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
