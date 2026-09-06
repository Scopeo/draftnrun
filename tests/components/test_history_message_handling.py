from openai.types.chat import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_message_tool_call import Function

from engine.components.history_message_handling import (
    TRUNCATED_CONTENT_NOTICE,
    HistoryMessageHandler,
    estimate_message_tokens,
)
from engine.components.types import ChatMessage


def make_message(role: str, content: str, tool_call_id: str | None = None) -> ChatMessage:
    return ChatMessage(role=role, content=content, tool_call_id=tool_call_id)


def make_tool_call_message(tool_call_id: str) -> ChatMessage:
    return ChatMessage(
        role="assistant",
        content=None,
        tool_calls=[
            ChatCompletionMessageToolCall(
                id=tool_call_id,
                type="function",
                function=Function(name="search", arguments="{}"),
            )
        ],
    )


def test_count_truncation_keeps_all_messages_when_short():
    handler = HistoryMessageHandler(number_first_messages=1, number_last_messages=5)
    messages = [make_message("system", "prompt")] + [make_message("user", f"q{i}") for i in range(3)]
    assert handler.get_truncated_messages_history(messages) == messages


def test_count_truncation_keeps_first_and_last_messages():
    handler = HistoryMessageHandler(number_first_messages=1, number_last_messages=2)
    messages = [
        make_message("system", "prompt"),
        make_message("user", "old question"),
        make_message("assistant", "old answer"),
        make_message("user", "new question"),
        make_message("assistant", "new answer"),
    ]
    truncated = handler.get_truncated_messages_history(messages)
    assert truncated == [messages[0], messages[3], messages[4]]


def test_token_budget_drops_oldest_messages_first():
    handler = HistoryMessageHandler(number_first_messages=1, number_last_messages=50, max_history_tokens=2_000)
    big_content = "x" * 3_000  # ~857 estimated tokens each
    messages = [
        make_message("system", "prompt"),
        make_message("user", big_content),
        make_message("assistant", big_content),
        make_message("user", big_content),
    ]
    truncated = handler.get_truncated_messages_history(messages)
    assert truncated[0] is messages[0]
    assert truncated[-1] is messages[-1]
    assert len(truncated) < len(messages)
    assert sum(estimate_message_tokens(message) for message in truncated) <= 2_000


def test_token_budget_drops_tool_call_turns_as_a_unit():
    handler = HistoryMessageHandler(number_first_messages=1, number_last_messages=50, max_history_tokens=1_500)
    big_tool_output = "x" * 4_000
    messages = [
        make_message("system", "prompt"),
        make_message("user", "question"),
        make_tool_call_message("call_1"),
        make_message("tool", big_tool_output, tool_call_id="call_1"),
        make_message("assistant", "answer"),
        make_message("user", "follow-up"),
    ]
    truncated = handler.get_truncated_messages_history(messages)
    for index, message in enumerate(truncated):
        if message.role == "tool":
            assert truncated[index - 1].role in ("assistant", "tool")
            assert any(prior.tool_calls for prior in truncated[:index])
    assert truncated[-1] is messages[-1]


def test_token_budget_shrinks_last_turn_with_huge_parallel_tool_results():
    # Production shape: one agent iteration with 4 parallel retriever calls,
    # each returning more content than the whole budget allows
    handler = HistoryMessageHandler(number_first_messages=1, number_last_messages=50, max_history_tokens=10_000)
    messages = [
        make_message("system", "prompt"),
        make_message("user", "old question"),
        make_message("assistant", "old answer"),
        make_message("user", "new question"),
        make_tool_call_message("call_1"),
    ] + [make_message("tool", "x" * 50_000, tool_call_id=f"call_{i}") for i in range(4)]
    truncated = handler.get_truncated_messages_history(messages)
    roles = [message.role for message in truncated]
    assert roles.count("tool") == 4
    assert truncated[roles.index("tool") - 1].tool_calls is not None
    assert sum(estimate_message_tokens(message) for message in truncated) <= 10_000


def test_token_budget_shrinks_single_oversized_message():
    handler = HistoryMessageHandler(number_first_messages=1, number_last_messages=50, max_history_tokens=1_000)
    messages = [
        make_message("system", "prompt"),
        make_message("user", "x" * 100_000),
    ]
    truncated = handler.get_truncated_messages_history(messages)
    assert len(truncated) == 2
    assert truncated[1].content.endswith(TRUNCATED_CONTENT_NOTICE)
    assert sum(estimate_message_tokens(message) for message in truncated) <= 1_000
    assert messages[1].content == "x" * 100_000  # Input messages are not mutated


def test_token_budget_disabled_returns_messages_unchanged():
    handler = HistoryMessageHandler(number_first_messages=1, number_last_messages=50, max_history_tokens=None)
    messages = [
        make_message("system", "prompt"),
        make_message("user", "x" * 1_000_000),
    ]
    assert handler.get_truncated_messages_history(messages) == messages
