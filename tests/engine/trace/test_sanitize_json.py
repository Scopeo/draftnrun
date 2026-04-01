import json

from engine.trace.sql_exporter import remove_null_bytes


class TestRemoveNullBytes:
    def test_string_with_null_byte(self):
        assert remove_null_bytes("hello\x00world") == "helloworld"

    def test_string_without_null_byte(self):
        assert remove_null_bytes("hello world") == "hello world"

    def test_dict_with_null_bytes(self):
        result = remove_null_bytes({"key": "val\x00ue", "nested": {"deep": "a\x00b"}})
        assert result == {"key": "value", "nested": {"deep": "ab"}}

    def test_list_with_null_bytes(self):
        result = remove_null_bytes(["a\x00b", "c\x00d"])
        assert result == ["ab", "cd"]

    def test_non_string_values_unchanged(self):
        result = remove_null_bytes({"count": 42, "flag": True, "empty": None})
        assert result == {"count": 42, "flag": True, "empty": None}

    def test_tuple_preserved(self):
        result = remove_null_bytes(("a\x00b", "cd"))
        assert result == ("ab", "cd")

    def test_empty_structures(self):
        assert remove_null_bytes({}) == {}
        assert remove_null_bytes([]) == []
        assert remove_null_bytes("") == ""

    def test_result_serializes_to_valid_json(self):
        data = {"content": "hello\x00world", "nested": ["\x00start", "end\x00"]}
        sanitized = remove_null_bytes(data)
        serialized = json.dumps(sanitized)
        parsed = json.loads(serialized)
        assert parsed == {"content": "helloworld", "nested": ["start", "end"]}

    def test_preserves_literal_emoji(self):
        data = {"content": "hello \U0001f60a world"}
        result = remove_null_bytes(data)
        assert result == data

    def test_preserves_valid_unicode(self):
        data = {"content": "caf\u00e9"}
        result = remove_null_bytes(data)
        assert result == data

    def test_backslash_u0000_literal_text_not_corrupted(self):
        """Regression: the old sanitize_json_string approach would corrupt literal '\\u0000'
        text in JSON by leaving a dangling backslash, causing JSONDecodeError."""
        data = {"content": "escape \\u0000something after"}
        sanitized = remove_null_bytes(data)
        assert sanitized == data
        serialized = json.dumps(sanitized)
        parsed = json.loads(serialized)
        assert parsed["content"] == "escape \\u0000something after"

    def test_dict_keys_sanitized(self):
        data = {"clean": 1, "nu\x00ll": 2, "nested": {"k\x00ey": "v\x00al"}}
        result = remove_null_bytes(data)
        assert result == {"clean": 1, "null": 2, "nested": {"key": "val"}}
        serialized = json.dumps(result)
        assert "\x00" not in serialized
        json.loads(serialized)

    def test_backslash_near_null_byte(self):
        """Backslash followed by an actual null byte: null is removed, backslash kept."""
        data = {"path": "C:\\\x00file"}
        sanitized = remove_null_bytes(data)
        assert sanitized == {"path": "C:\\file"}
        serialized = json.dumps(sanitized)
        json.loads(serialized)
