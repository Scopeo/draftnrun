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

    def test_removes_lone_surrogates(self):
        text = r'[{"content": "emoji \ud83c here"}]'
        result = sanitize_json_string(text)
        assert "\\ud83c" not in result
        json.loads(result)

    def test_removes_high_and_low_surrogates(self):
        text = r'[{"content": "pair \uD83D\uDE0A done"}]'
        result = sanitize_json_string(text)
        assert "\\uD83D" not in result
        assert "\\uDE0A" not in result
        json.loads(result)

    def test_fixes_invalid_escape_backslash_exclamation(self):
        text = r'[{"content": "Bravo\!"}]'
        result = sanitize_json_string(text)
        parsed = json.loads(result)
        assert parsed[0]["content"] == "Bravo!"

    def test_fixes_invalid_escape_backslash_comma(self):
        text = r'[{"content": "a\,b"}]'
        result = sanitize_json_string(text)
        parsed = json.loads(result)
        assert parsed[0]["content"] == "a,b"

    def test_fixes_invalid_escape_backslash_J(self):
        text = r'[{"content": "test\Jvalue"}]'
        result = sanitize_json_string(text)
        parsed = json.loads(result)
        assert parsed[0]["content"] == "testJvalue"

    def test_preserves_valid_escapes(self):
        text = r'[{"content": "line1\nline2\ttab\\backslash\"quote"}]'
        result = sanitize_json_string(text)
        assert result == text
        parsed = json.loads(result)
        assert "line1\nline2\ttab\\backslash\"quote" == parsed[0]["content"]

    def test_preserves_valid_unicode_escapes(self):
        text = r'[{"content": "caf\u00e9"}]'
        result = sanitize_json_string(text)
        assert result == text
        parsed = json.loads(result)
        assert parsed[0]["content"] == "caf\u00e9"

    def test_combined_issues(self):
        text = r'[{"content": "hello\u0000world\! emoji\ud83c done\,end"}]'
        result = sanitize_json_string(text)
        parsed = json.loads(result)
        assert "\\u0000" not in result
        assert parsed[0]["content"] == "helloworld! emoji done,end"

    def test_unfixable_json_returns_empty_array(self):
        broken = '{"content": "unterminated string\\'
        result = sanitize_json_string(broken)
        assert result == "[]"

    def test_empty_array(self):
        assert sanitize_json_string("[]") == "[]"

    def test_empty_object(self):
        assert sanitize_json_string("{}") == "{}"
