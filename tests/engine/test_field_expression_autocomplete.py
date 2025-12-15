from engine.field_expressions.autocomplete import (
    FieldExpressionSuggestionKind,
    get_cursor_context,
)


def test_get_cursor_context_returns_none_outside_reference():
    text = "plain text without refs"
    assert get_cursor_context(text, len(text)) is None


def test_get_cursor_context_instance_phase_with_partial_prefix():
    instance_prefix = "abc123"
    text = "prefix @{{" + instance_prefix
    ctx = get_cursor_context(text, len(text))
    assert ctx is not None
    assert ctx.phase == FieldExpressionSuggestionKind.INSTANCE
    assert ctx.instance_prefix == instance_prefix


def test_get_cursor_context_port_phase():
    text = "@{{node-1.output"
    cursor_offset = text.index(".output") + len(".out")
    ctx = get_cursor_context(text, cursor_offset)
    assert ctx is not None
    assert ctx.phase == FieldExpressionSuggestionKind.PORT
    assert ctx.instance_prefix == "node-1"
    assert ctx.port_prefix == "out"


def test_get_cursor_context_key_phase():
    text = "@{{node.port::doc"
    ctx = get_cursor_context(text, len(text))
    assert ctx is not None
    assert ctx.phase == FieldExpressionSuggestionKind.KEY
    assert ctx.port_prefix == "port"
    assert ctx.key_prefix == "doc"


def test_get_cursor_context_ignores_closed_reference():
    text = "@{{node.port}} trailing"
    assert get_cursor_context(text, len(text)) is None
