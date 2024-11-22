#!/usr/bin/env python

import click
import json
from apolo_sdk import JobRestartPolicy
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, TypeAdapter
from pydantic.json_schema import SkipJsonSchema
from typing import Annotated, Any, Literal

from apolo_flow import ast


TIMEDELTA_RE = r"^((?P<d>\d+)d)?((?P<h>\d+)h)?((?P<m>\d+)m)?((?P<s>\d+)s)?$"


def pop_default_from_schema(s: dict[str, Any]) -> None:
    s.pop("default", None)


class Cache(BaseModel, use_enum_values=True, extra="forbid"):
    strategy: ast.CacheStrategy
    life_span: str | SkipJsonSchema[None] = Field(
        default=None, pattern=TIMEDELTA_RE, json_schema_extra=pop_default_from_schema
    )


class Param(BaseModel, use_enum_values=True, extra="forbid"):
    default: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    descr: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class Strategy(BaseModel, use_enum_values=True, extra="forbid"):
    matrix: dict[str, list[str | dict[str, str]]] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    fail_fast: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    max_parallel: int | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class Image(BaseModel, use_enum_values=True, extra="forbid"):
    ref: str
    context: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    dockerfile: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    build_args: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    env: dict[str, str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    build_preset: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    force_rebuild: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    extra_kaniko_args: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class Volume(BaseModel, use_enum_values=True, extra="forbid"):
    remote: str
    mount: str
    read_only: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    local: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class ExecUnit(BaseModel, use_enum_values=True, extra="forbid"):
    title: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    name: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    image: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    preset: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    schedule_timeout: str | SkipJsonSchema[None] = Field(
        default=None, pattern=TIMEDELTA_RE, json_schema_extra=pop_default_from_schema
    )
    entrypoint: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    cmd: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    bash: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    python: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    workdir: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    env: dict[str, str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    tags: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    life_span: str | SkipJsonSchema[None] = Field(
        default=None, pattern=TIMEDELTA_RE, json_schema_extra=pop_default_from_schema
    )
    http_port: int | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    http_auth: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    pass_config: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    restart: JobRestartPolicy | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class ExecUnitMixin(ExecUnit, use_enum_values=True, extra="forbid"):
    mixins: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class JobMixin(ExecUnit, use_enum_values=True, extra="forbid"):
    detach: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    browse: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    multi: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    port_forward: str | SkipJsonSchema[None] = Field(
        default=None, pattern=r"^\d+:\d+$", json_schema_extra=pop_default_from_schema
    )
    params: dict[str, str | Param] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    mixins: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class TaskMixin(ExecUnit, use_enum_values=True, extra="forbid"):
    mixins: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class TaskBase(BaseModel, use_enum_values=True, extra="forbid"):
    id: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    needs: list[str] = Field(default=None, json_schema_extra=pop_default_from_schema)
    strategy: list[Strategy] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    enable: bool | str = Field(default=None, json_schema_extra=pop_default_from_schema)
    cache: Cache | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class Task(TaskBase, use_enum_values=True, extra="forbid"):
    pass


class BaseDefaults(BaseModel, use_enum_values=True, extra="forbid"):
    tags: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    env: dict[str, str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    workdir: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    life_span: str | SkipJsonSchema[None] = Field(
        default=None, pattern=TIMEDELTA_RE, json_schema_extra=pop_default_from_schema
    )
    preset: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    schedule_timeout: str | SkipJsonSchema[None] = Field(
        default=None, pattern=TIMEDELTA_RE, json_schema_extra=pop_default_from_schema
    )


class ExtendedDefaults(BaseModel, use_enum_values=True, extra="forbid"):
    fail_fast: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    max_parallel: int | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    cache: Cache | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class LiveDefaults(BaseDefaults, use_enum_values=True, extra="forbid"):
    pass


class BaseFlow(BaseModel, use_enum_values=True, extra="forbid"):
    id: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    title: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    life_span: str | SkipJsonSchema[None] = Field(
        default=None, pattern=TIMEDELTA_RE, json_schema_extra=pop_default_from_schema
    )
    images: dict[str, Image] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: dict[str, Volume] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class LiveFlow(BaseModel, use_enum_values=True, extra="forbid"):
    kind: Literal["live"]
    params: dict[str, str | Param] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    defaults: LiveDefaults | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    mixins: dict[str, JobMixin] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class BatchDefaults(ExtendedDefaults, use_enum_values=True, extra="forbid"):
    pass


class BatchFlow(BaseModel, use_enum_values=True, extra="forbid"):
    kind: Literal["batch"]
    defaults: BatchDefaults | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    mixins: dict[str, TaskMixin] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )

    tasks: list[Task]


FLOW = TypeAdapter(
    Annotated[
        Annotated[LiveFlow, Tag("live")] | Annotated[BatchFlow, Tag("batch")],
        Discriminator("kind"),
    ],
    config=ConfigDict(
        title="Flow",
        extra="forbid",
    ),
)


class ProjectDefaults(ExtendedDefaults, use_enum_values=True, extra="forbid"):
    pass


class Project(BaseModel, use_enum_values=True, extra="forbid"):
    id: str
    project_name: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    owner: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    role: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    images: dict[str, Image] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: dict[str, Volume] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    defaults: ProjectDefaults | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    mixins: dict[str, ExecUnitMixin] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


@click.command()
def main() -> None:
    here = Path(__file__)
    toplevel = here.parent.parent
    package = toplevel / "src" / "apolo_flow"

    flow_schema = package / "flow-schema.json"
    with flow_schema.open("w") as f:
        f.write(json.dumps(FLOW.json_schema(), indent=2))

    project_schema = package / "project-schema.json"
    with project_schema.open("w") as f:
        f.write(json.dumps(Project.model_json_schema(), indent=2))


if __name__ == "__main__":
    main()
