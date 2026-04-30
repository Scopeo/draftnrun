import pytest

from ada_backend.schemas.prompt_schema import DiffOperation
from ada_backend.services.prompt_service import compute_prompt_diff


class TestComputePromptDiff:
    def test_identical_content_returns_empty(self):
        ops = compute_prompt_diff("hello world", "hello world")
        assert ops == []

    def test_insert_only(self):
        ops = compute_prompt_diff("hello", "hello world")
        assert len(ops) == 1
        assert ops[0].op == "insert"
        assert ops[0].from_start == 5
        assert ops[0].from_end == 5
        assert ops[0].to_start == 5
        assert ops[0].to_end == 11

    def test_delete_only(self):
        ops = compute_prompt_diff("hello world", "hello")
        assert len(ops) == 1
        assert ops[0].op == "delete"

    def test_replace(self):
        ops = compute_prompt_diff("abc", "axc")
        assert len(ops) >= 1
        assert any(op.op == "replace" for op in ops)

    def test_complex_diff(self):
        old = "You are a helpful assistant.\nRespond concisely."
        new = "You are a friendly assistant.\nRespond in detail.\nAlways be polite."
        ops = compute_prompt_diff(old, new)
        assert len(ops) > 0
        for op in ops:
            assert op.op in ("insert", "delete", "replace")
            assert op.from_start <= op.from_end
            assert op.to_start <= op.to_end

    def test_empty_to_content(self):
        ops = compute_prompt_diff("", "new content")
        assert len(ops) == 1
        assert ops[0].op == "insert"

    def test_content_to_empty(self):
        ops = compute_prompt_diff("old content", "")
        assert len(ops) == 1
        assert ops[0].op == "delete"

    def test_large_prompt_diff(self):
        old = "A" * 10000
        new = "A" * 5000 + "B" * 5000
        ops = compute_prompt_diff(old, new)
        assert len(ops) > 0


class TestDiffOperation:
    def test_schema_validation(self):
        op = DiffOperation(op="insert", from_start=0, from_end=0, to_start=0, to_end=5)
        assert op.op == "insert"

    def test_all_op_types(self):
        for op_type in ("equal", "insert", "delete", "replace"):
            op = DiffOperation(op=op_type, from_start=0, from_end=1, to_start=0, to_end=1)
            assert op.op == op_type

    def test_invalid_op_raises(self):
        with pytest.raises(Exception):
            DiffOperation(op="invalid", from_start=0, from_end=0, to_start=0, to_end=0)
