import json

from ada_backend.services.metrics.utils import _extract_preview


class TestExtractPreview:
    def test_none_returns_empty(self):
        assert _extract_preview(None) == ""

    def test_empty_string_returns_empty(self):
        assert _extract_preview("") == ""

    def test_simple_content_field(self):
        raw = json.dumps([{"content": "Hello world"}])
        assert _extract_preview(raw) == "Hello world"

    def test_messages_extracts_last_message_content(self):
        raw = json.dumps([
            {
                "messages": [
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "What is 2+2?"},
                ]
            }
        ])
        assert _extract_preview(raw) == "What is 2+2?"

    def test_large_payload_with_messages_and_extra_keys(self):
        """Regression: payloads with messages + large sibling keys (e.g. job descriptions)
        must still extract the last message content."""
        raw = json.dumps([
            {
                "messages": [{"role": "user", "content": "260480"}],
                "conversation_id": "cb9eb611-de77-4465-8216-4f3edec9a18b",
                "job": {
                    "job": {"id": 264898, "title": "RESPONSABLE COMMERCIAL", "details": {"description": "x" * 10000}}
                },
            }
        ])
        assert _extract_preview(raw) == "260480"

    def test_truncates_long_content(self):
        raw = json.dumps([{"content": "a" * 1000}])
        assert len(_extract_preview(raw)) == 500

    def test_plain_string_element(self):
        raw = json.dumps(["just a string"])
        assert _extract_preview(raw) == "just a string"

    def test_dict_not_in_list(self):
        raw = json.dumps({"key": "value"})
        result = _extract_preview(raw)
        assert "key" in result

    def test_truncated_json_fallback_extracts_content(self):
        full = json.dumps([
            {
                "messages": [{"role": "user", "content": "260480"}],
                "job": {"details": "x" * 10000},
            }
        ])
        truncated = full[:5000]
        result = _extract_preview(truncated)
        assert result == "260480"

    def test_assistant_output_with_large_stringified_json_content(self):
        """Regression: assistant output where content is a large stringified JSON object
        (e.g. job processing results) must extract the content field as preview."""
        inner_json = json.dumps({
            "job": {"id": 264898, "title": "RESPONSABLE COMMERCIAL", "details": {"description": "x" * 10000}}
        })
        raw = json.dumps([
            {
                "content": inner_json,
                "refusal": None,
                "role": "assistant",
                "annotations": None,
                "audio": None,
                "function_call": None,
                "tool_calls": None,
            }
        ])
        result = _extract_preview(raw)
        assert len(result) == 500
        assert result == inner_json[:500]

    def test_truncated_json_fallback_returns_raw_slice(self):
        truncated = "not json at all, no content field"
        result = _extract_preview(truncated)
        assert result == truncated
