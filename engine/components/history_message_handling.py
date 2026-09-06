import json

from engine.components.types import ChatMessage

MINIMAL_FIRST_MESSAGE_RETAINED = 1  # To retain the prompt system message
MINIMAL_LAST_MESSAGE_RETAINED = 50
APPROXIMATE_CHARS_PER_TOKEN = 3.5
# Conservative budget: keeps the estimated prompt size below the smallest context
# windows of the supported providers (Anthropic 200k, OpenAI 128k), leaving room
# for tool descriptions and the model response.
DEFAULT_MAX_HISTORY_TOKENS = 100_000
TRUNCATED_CONTENT_NOTICE = "\n\n[Content truncated because the conversation exceeded the model context window]"


def _estimate_text_tokens(text: str) -> int:
    return int(len(text) / APPROXIMATE_CHARS_PER_TOKEN)


def estimate_message_tokens(message: ChatMessage) -> int:
    char_count = 0
    if isinstance(message.content, str):
        char_count += len(message.content)
    elif isinstance(message.content, list):
        char_count += sum(len(str(item)) for item in message.content if item)
    if message.tool_calls:
        char_count += len(json.dumps([tool_call.model_dump() for tool_call in message.tool_calls], default=str))
    return int(char_count / APPROXIMATE_CHARS_PER_TOKEN)


def _estimate_total_tokens(messages: list[ChatMessage]) -> int:
    return sum(estimate_message_tokens(message) for message in messages)


def _flatten(units: list[list[ChatMessage]]) -> list[ChatMessage]:
    return [message for unit in units for message in unit]


class HistoryMessageHandler:
    def __init__(
        self,
        number_first_messages: int = MINIMAL_FIRST_MESSAGE_RETAINED,
        number_last_messages: int = MINIMAL_LAST_MESSAGE_RETAINED,
        max_history_tokens: int | None = DEFAULT_MAX_HISTORY_TOKENS,
    ):
        self.number_first_messages = number_first_messages
        self.number_last_messages = number_last_messages
        self.max_history_tokens = max_history_tokens

    def get_truncated_messages_history(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        truncated_by_count = self._truncate_by_message_count(messages)
        return self._truncate_by_token_budget(truncated_by_count)

    def _truncate_by_message_count(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if self.number_first_messages is None or self.number_last_messages is None:
            raise ValueError("No numbers of messages to find initial context and end of history were provided.")

        num_total = len(messages)
        if num_total <= self.number_first_messages + self.number_last_messages:
            return messages  # Overlap case: return all messages

        first_part = messages[: self.number_first_messages]
        last_part = messages[-self.number_last_messages :]

        # Check for overlap via role conflict only if needed
        if first_part[-1].role != last_part[0].role:
            return first_part + last_part
        else:
            # We still assume there is an alternating pattern of role and that last messages
            # have more than one message
            return first_part + last_part[1:]

    def _truncate_by_token_budget(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if self.max_history_tokens is None:
            return messages
        if _estimate_total_tokens(messages) <= self.max_history_tokens:
            return messages

        first_part = list(messages[: self.number_first_messages])
        tail_units = self._group_into_tool_call_units(messages[self.number_first_messages :])
        while len(tail_units) > 1 and (
            _estimate_total_tokens(first_part + _flatten(tail_units)) > self.max_history_tokens
            or tail_units[0][0].role == "tool"
        ):
            tail_units.pop(0)
        return self._shrink_oversized_contents(first_part + _flatten(tail_units))

    @staticmethod
    def _group_into_tool_call_units(messages: list[ChatMessage]) -> list[list[ChatMessage]]:
        # A tool result without its preceding assistant tool_calls message is an invalid
        # request, so an assistant message and its tool results are dropped as one unit
        units: list[list[ChatMessage]] = []
        for message in messages:
            if message.role == "tool" and units:
                units[-1].append(message)
            else:
                units.append([message])
        return units

    def _shrink_oversized_contents(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        excess_tokens = _estimate_total_tokens(messages) - self.max_history_tokens
        if excess_tokens <= 0:
            return messages

        shrunk = list(messages)
        indices_largest_first = sorted(
            range(len(shrunk)), key=lambda index: estimate_message_tokens(shrunk[index]), reverse=True
        )
        notice_tokens = _estimate_text_tokens(TRUNCATED_CONTENT_NOTICE)
        for index in indices_largest_first:
            if excess_tokens <= 0:
                break
            message = shrunk[index]
            if not isinstance(message.content, str):
                continue
            content_tokens = _estimate_text_tokens(message.content)
            tokens_to_remove = min(excess_tokens + notice_tokens, content_tokens)
            if tokens_to_remove <= 0:
                continue
            chars_to_keep = int((content_tokens - tokens_to_remove) * APPROXIMATE_CHARS_PER_TOKEN)
            shrunk[index] = message.model_copy(
                update={"content": message.content[:chars_to_keep] + TRUNCATED_CONTENT_NOTICE}
            )
            excess_tokens -= tokens_to_remove - notice_tokens
        return shrunk
