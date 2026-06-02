from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage

from engine.llm_services.providers.google_provider import GoogleProvider


def create_mock_completion(content: str = "The weather in Paris is sunny.") -> ChatCompletion:
    return ChatCompletion(
        id="test-id",
        object="chat.completion",
        created=1234567890,
        model="gemini-test",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=CompletionUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


def create_weather_tool() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather information",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }


@pytest.mark.asyncio
async def test_google_function_call_converts_tool_response_history():
    provider = GoogleProvider(api_key="test-key", base_url="https://test.com", model_name="gemini-test")
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=create_mock_completion())

    messages = [
        {"role": "user", "content": "What's the weather in Paris?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Weather in Paris: Sunny, 22°C"},
    ]

    with patch("engine.llm_services.providers.google_provider.openai.AsyncOpenAI", return_value=client):
        response, prompt_tokens, completion_tokens, total_tokens = await provider.function_call_without_structured_output(
            messages=messages,
            tools=[create_weather_tool()],
            tool_choice="auto",
            temperature=1,
            stream=False,
        )

    sent_messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert sent_messages == [
        {"role": "user", "content": "What's the weather in Paris?"},
        {"role": "user", "content": "Tool get_weather returned: Weather in Paris: Sunny, 22°C"},
    ]
    assert response.choices[0].message.content == "The weather in Paris is sunny."
    assert (prompt_tokens, completion_tokens, total_tokens) == (10, 20, 30)
