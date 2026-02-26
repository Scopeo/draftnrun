import pytest

from ada_backend.services.graph.output_port_instance_sync import extract_schema_keys


class TestExtractSchemaKeysWithDict:
    def test_returns_keys_from_dict(self):
        assert extract_schema_keys({"name": "string", "age": "number"}) == ["name", "age"]

    def test_returns_single_key_from_dict(self):
        assert extract_schema_keys({"output": "string"}) == ["output"]

    def test_returns_empty_list_for_empty_dict(self):
        assert extract_schema_keys({}) == []

    def test_preserves_key_order(self):
        value = {"z": "string", "a": "number", "m": "boolean"}
        assert extract_schema_keys(value) == ["z", "a", "m"]


class TestExtractSchemaKeysWithJsonString:
    def test_returns_keys_from_valid_json_string(self):
        assert extract_schema_keys('{"name": "string", "age": "number"}') == ["name", "age"]

    def test_returns_empty_list_for_empty_json_object_string(self):
        assert extract_schema_keys("{}") == []

    def test_returns_empty_list_for_invalid_json(self):
        assert extract_schema_keys("not valid json") == []

    def test_returns_empty_list_for_json_array_string(self):
        assert extract_schema_keys('["name", "age"]') == []

    def test_returns_empty_list_for_json_scalar_string(self):
        assert extract_schema_keys('"just a string"') == []

    def test_returns_empty_list_for_json_number_string(self):
        assert extract_schema_keys("42") == []


class TestExtractSchemaKeysWithInvalidTypes:
    @pytest.mark.parametrize("value", [None, 42, 3.14, True, ["a", "b"], object()])
    def test_returns_empty_list_for_unsupported_types(self, value):
        assert extract_schema_keys(value) == []
