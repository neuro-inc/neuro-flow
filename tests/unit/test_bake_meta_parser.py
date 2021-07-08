import pathlib
import pytest
from yaml.constructor import ConstructorError

from neuro_flow.parser import parse_bake_meta


def test_dict_correct(assets: pathlib.Path) -> None:
    config_file = assets / "bake_meta" / "ok.yml"
    flow = parse_bake_meta(config_file)
    assert flow == {
        "foo": "22",
        "bar": "test",
    }


def test_not_flat_invalid(assets: pathlib.Path) -> None:
    config_file = assets / "bake_meta" / "not_flat.yml"
    with pytest.raises(ConstructorError):
        parse_bake_meta(config_file)


def test_not_dict_invalid(assets: pathlib.Path) -> None:
    config_file = assets / "bake_meta" / "not_dict.yml"
    with pytest.raises(ConstructorError):
        parse_bake_meta(config_file)
