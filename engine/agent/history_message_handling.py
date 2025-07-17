from engine.agent.data_structures import ChatMessage

MINIMAL_FIRST_MESSAGE_RETAINED = 1  # To retain the prompt system message
MINIMAL_LAST_MESSAGE_RETAINED = 50


class HistoryMessageHandler:
    def __init__(
        self,
        number_first_messages: int = MINIMAL_FIRST_MESSAGE_RETAINED,
        number_last_messages: int = MINIMAL_LAST_MESSAGE_RETAINED,
    ):
        self.number_first_messages = number_first_messages
        self.number_last_messages = number_last_messages

    def get_truncated_messages_history(self, messages: list[ChatMessage]) -> list[ChatMessage]:
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
