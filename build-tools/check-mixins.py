#!/usr/bin/env python3

import dataclasses

from typing import AbstractSet, Type

from neuro_flow import ast, expr


def check_mixin(
    base: Type[ast.Base], mixin: Type[ast.Base], allowed_extra_fields: AbstractSet[str]
) -> None:
    base_fields = {f.name: f for f in dataclasses.fields(base)}
    mixin_fields = {f.name: f for f in dataclasses.fields(mixin)}

    base_keys = set(base_fields.keys()) - allowed_extra_fields
    mixin_keys = set(mixin_fields.keys())
    if base_keys != mixin_keys:
        missing = base_keys - mixin_keys
        additional = mixin_keys - base_keys
        print(f"Fields in {base.__name__} and {mixin.__name__} differ:")
        if missing:
            print(f"Mixin doesn't have field(s): {', '.join(missing)}")
        if additional:
            print(f"Mixin has additional field(s): {', '.join(additional)}")
        exit(1)

    for field_name in base_keys:
        base_field = base_fields[field_name]
        mixin_field = mixin_fields[field_name]

        types_match = (base_field.type == mixin_field.type) or (
            issubclass(mixin_field.type, expr.Expr)
            and issubclass(base_field.type, expr.Expr)
            and base_field.type.type == mixin_field.type.type
        )
        if not types_match:
            print(f"Type of {base.__name__} and {mixin.__name__} field differ:")
            print(f"{base.__name__}.{field_name} is {base_field.type}")
            print(f"{mixin.__name__}.{field_name} is {mixin_field.type}")
            exit(1)


if __name__ == "__main__":
    check_mixin(ast.Job, ast.JobMixin, allowed_extra_fields=set())
    check_mixin(ast.Task, ast.TaskMixin, allowed_extra_fields={"id"})
