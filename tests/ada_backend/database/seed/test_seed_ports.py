"""Regression tests for get_parameter_type — Python type annotation inference."""

from typing import Any, Optional

from pydantic import Field
from pydantic.fields import FieldInfo

from ada_backend.database.models import ParameterType
from ada_backend.database.seed.seed_ports import get_parameter_type


def _field(annotation, **kwargs) -> FieldInfo:
    """Build a FieldInfo with the given annotation for testing."""
    info = Field(**kwargs)
    info.annotation = annotation
    return info


def test_explicit_parameter_type_wins():
    info = _field(str, json_schema_extra={"parameter_type": "json"})
    assert get_parameter_type(info) == ParameterType.JSON


def test_str_annotation():
    assert get_parameter_type(_field(str)) == ParameterType.STRING


def test_int_annotation():
    assert get_parameter_type(_field(int)) == ParameterType.INTEGER


def test_float_annotation():
    assert get_parameter_type(_field(float)) == ParameterType.FLOAT


def test_bool_annotation():
    assert get_parameter_type(_field(bool)) == ParameterType.BOOLEAN


def test_dict_annotation():
    assert get_parameter_type(_field(dict)) == ParameterType.JSON


def test_optional_dict_annotation():
    assert get_parameter_type(_field(Optional[dict])) == ParameterType.JSON


def test_dict_str_any_annotation():
    assert get_parameter_type(_field(dict[str, Any])) == ParameterType.JSON


def test_list_annotation():
    assert get_parameter_type(_field(list)) == ParameterType.ARRAY


def test_optional_list_str_annotation():
    assert get_parameter_type(_field(Optional[list[str]])) == ParameterType.ARRAY


def test_optional_str_stays_string():
    assert get_parameter_type(_field(Optional[str])) == ParameterType.STRING
