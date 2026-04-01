import json

from engine.trace.sql_exporter import sanitize_json_string


class TestSanitizeJsonString:
    def test_valid_json_unchanged(self):
        text = json.dumps([{"role": "assistant", "content": "Hello world"}])
        assert sanitize_json_string(text) == text

    def test_removes_null_byte_escape(self):
        text = r'[{"content": "hello\u0000world"}]'
        result = sanitize_json_string(text)
        assert "\\u0000" not in result
        parsed = json.loads(result)
        assert parsed[0]["content"] == "helloworld"

    def test_preserves_surrogate_pairs(self):
        text = r'[{"content": "pair \uD83D\uDE0A done"}]'
        result = sanitize_json_string(text)
        assert "\\uD83D" in result
        assert "\\uDE0A" in result
        parsed = json.loads(result)
        assert "\U0001f60a" in parsed[0]["content"]

    def test_preserves_valid_escapes(self):
        text = r'[{"content": "line1\nline2\ttab\\backslash\"quote"}]'
        result = sanitize_json_string(text)
        assert result == text

    def test_preserves_valid_unicode_escapes(self):
        text = r'[{"content": "caf\u00e9"}]'
        result = sanitize_json_string(text)
        assert result == text
        parsed = json.loads(result)
        assert parsed[0]["content"] == "caf\u00e9"

    def test_preserves_literal_emoji(self):
        text = json.dumps([{"content": "hello \U0001f60a world"}])
        result = sanitize_json_string(text)
        parsed = json.loads(result)
        assert "\U0001f60a" in parsed[0]["content"]

    def test_empty_array(self):
        assert sanitize_json_string("[]") == "[]"

    def test_empty_object(self):
        assert sanitize_json_string("{}") == "{}"
