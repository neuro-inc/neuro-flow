#!/usr/bin/env python

import click
import json
from apolo_sdk import JobRestartPolicy
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, TypeAdapter
from pydantic.json_schema import SkipJsonSchema
from typing import Annotated, Any, Literal

from apolo_flow import ast


LiteralT = int | float | str | bool

EXPR = Annotated[str, Field(pattern=r"^\$\{\{.+\}\}$")]

TIMEDELTA_CONST = Annotated[str, Field(pattern=r"^(\d+d)?(\d+h)?(\d+m)?(\d+s)?$")]
TIMEDELTA = TIMEDELTA_CONST | EXPR

PORT_FORWARD_CONST = Annotated[str, Field(pattern=r"^\d+:\d+$")]
PORT_FORWARD = PORT_FORWARD_CONST | EXPR


def pop_default_from_schema(s: dict[str, Any]) -> None:
    s.pop("default", None)


class Cache(BaseModel, use_enum_values=True, extra="forbid"):
    strategy: ast.CacheStrategy
    life_span: TIMEDELTA | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class Param(BaseModel, use_enum_values=True, extra="forbid"):
    default: LiteralT | None | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    descr: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class Strategy(BaseModel, use_enum_values=True, extra="forbid"):
    #    matrix: Any
    matrix: (
        dict[str, bool | int | EXPR | list[LiteralT | dict[str, LiteralT]]]
        | SkipJsonSchema[None]
    ) = Field(default=None, json_schema_extra=pop_default_from_schema)
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
    build_args: list[str] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    env: dict[str, str] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: list[str | None] | EXPR | SkipJsonSchema[None] = Field(
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
    schedule_timeout: TIMEDELTA | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
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
    action: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    module: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    args: dict[str, LiteralT | None] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    workdir: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    env: dict[str, str] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: list[str | None] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    tags: list[str] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    life_span: TIMEDELTA | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    http_port: int | str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    http_auth: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    pass_config: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    restart: JobRestartPolicy | EXPR | SkipJsonSchema[None] = Field(
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
    port_forward: list[PORT_FORWARD] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    params: dict[str, LiteralT | Param | None] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    mixins: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class Job(ExecUnit, use_enum_values=True, extra="forbid"):
    detach: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    browse: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    multi: bool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    port_forward: list[PORT_FORWARD] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    params: dict[str, LiteralT | Param | None] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    mixins: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class JobActionCall(BaseModel, use_enum_values=True, extra="forbid"):
    action: str
    args: dict[str, LiteralT] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    params: dict[str, str | Param] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class JobModuleCall(BaseModel, use_enum_values=True, extra="forbid"):
    module: str
    args: dict[str, LiteralT] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    params: dict[str, Param | EXPR] | SkipJsonSchema[None] = Field(
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
    needs: list[str] | dict[str, str] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    strategy: Strategy | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    enable: bool | str = Field(default=None, json_schema_extra=pop_default_from_schema)
    cache: Cache | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class Task(TaskBase, ExecUnit, use_enum_values=True, extra="forbid"):
    mixins: list[str] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class BaseDefaults(BaseModel, use_enum_values=True, extra="forbid"):
    tags: list[str] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    env: dict[str, str] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: list[str | None] | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    workdir: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    life_span: TIMEDELTA | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    preset: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    schedule_timeout: TIMEDELTA | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class ExtendedDefaults(BaseDefaults, use_enum_values=True, extra="forbid"):
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
    life_span: TIMEDELTA | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    images: dict[str, Image] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    volumes: dict[str, Volume] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    params: dict[str, str | Param] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class LiveFlow(BaseFlow, use_enum_values=True, extra="forbid"):
    kind: Literal["live"]
    defaults: LiveDefaults | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    mixins: dict[str, JobMixin] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    jobs: dict[str, Job | JobActionCall | JobModuleCall]


class BatchDefaults(ExtendedDefaults, use_enum_values=True, extra="forbid"):
    pass


class BatchFlow(BaseFlow, use_enum_values=True, extra="forbid"):
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


class ActionInput(BaseModel, use_enum_values=True, extra="forbid"):
    type: Literal["int"] | Literal["float"] | Literal["bool"] | Literal["str"] = "str"
    descr: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    default: LiteralT | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class ActionOutput(BaseModel, use_enum_values=True, extra="forbid"):
    descr: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    value: LiteralT | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class BaseAction(BaseModel, use_enum_values=True, extra="forbid"):
    name: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    author: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    descr: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    inputs: dict[str, ActionInput] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    # list[str] is for outputs.needs
    outputs: dict[str, ActionOutput | list[str]] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class LiveAction(BaseAction, use_enum_values=True, extra="forbid"):
    kind: Literal["live"]
    job: Job


class BatchAction(BaseAction, use_enum_values=True, extra="forbid"):
    kind: Literal["batch"]
    cache: Cache | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    images: dict[str, Image] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    tasks: list[Task]


class StatefulAction(BaseAction, use_enum_values=True, extra="forbid"):
    kind: Literal["stateful"]
    cache: Cache | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    main: ExecUnit | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    post: ExecUnit | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    post_if: bool | EXPR | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


class LocalAction(BaseAction, use_enum_values=True, extra="forbid"):
    kind: Literal["local"]
    cmd: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    bash: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )
    python: str | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=pop_default_from_schema
    )


ACTION = TypeAdapter(
    Annotated[
        Annotated[LiveAction, Tag("live")]
        | Annotated[BatchAction, Tag("batch")]
        | Annotated[StatefulAction, Tag("stateful")]
        | Annotated[LocalAction, Tag("local")],
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
    #        f.write(json.dumps(LiveFlow.model_json_schema(), indent=2))

    project_schema = package / "project-schema.json"
    with project_schema.open("w") as f:
        f.write(json.dumps(Project.model_json_schema(), indent=2))

    action_schema = package / "action-schema.json"
    with action_schema.open("w") as f:
        f.write(json.dumps(ACTION.json_schema(), indent=2))


if __name__ == "__main__":
    main()
