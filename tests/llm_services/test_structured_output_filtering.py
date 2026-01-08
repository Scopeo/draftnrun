import json
from unittest.mock import AsyncMock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from openai.types.completion_usage import CompletionUsage

from engine.llm_services.providers.anthropic_provider import AnthropicProvider
from engine.llm_services.providers.cerebras_provider import CerebrasProvider
from engine.llm_services.providers.custom_provider import CustomProvider
from engine.llm_services.providers.google_provider import GoogleProvider
from engine.llm_services.providers.mistral_provider import MistralProvider


def create_mock_completion(
    content: str | None = None,
    tool_calls: list[ChatCompletionMessageToolCall] | None = None,
    model: str = "test-model",
) -> ChatCompletion:
    return ChatCompletion(
        id="test-id",
        object="chat.completion",
        created=1234567890,
        model=model,
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls,
                ),
                finish_reason="stop",
            )
        ],
        usage=CompletionUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        ),
    )


def create_structured_output_tool() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "structured_output",
            "description": "Output structured data",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["answer", "confidence"],
            },
        },
    }


def create_regular_tool() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    }


@pytest.fixture
def providers():
    return [
        GoogleProvider(api_key="test-key", base_url="https://test.com", model_name="test-model"),
        AnthropicProvider(api_key="test-key", base_url="https://test.com", model_name="test-model"),
        MistralProvider(api_key="test-key", base_url="https://test.com", model_name="test-model"),
        CerebrasProvider(api_key="test-key", base_url="https://test.com", model_name="test-model"),
        CustomProvider(
            api_key="test-key",
            base_url="https://test.com",
            model_name="test-model",
            provider_name="custom",
        ),
    ]


class TestStructuredOutputFiltering:
    @pytest.mark.asyncio
    async def test_only_structured_output_tool_called(self, providers):
        structured_output_tool = create_structured_output_tool()
        regular_tool = create_regular_tool()
        structured_data = {"answer": "The answer is 42", "confidence": 0.95}

        for provider in providers:
            mock_response = create_mock_completion(
                tool_calls=[
                    ChatCompletionMessageToolCall(
                        id="call_1",
                        type="function",
                        function=Function(
                            name="structured_output",
                            arguments=json.dumps(structured_data),
                        ),
                    )
                ]
            )

            with patch.object(
                provider, "function_call_without_structured_output", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = (mock_response, 10, 20, 30)

                result, _, _, _ = await provider.function_call_with_structured_output(
                    messages=[{"role": "user", "content": "What is the answer?"}],
                    tools=[regular_tool],
                    tool_choice="required",
                    structured_output_tool=structured_output_tool,
                    temperature=0.7,
                    stream=False,
                )

                assert result.choices[0].message.content == json.dumps(structured_data, ensure_ascii=False)
                assert result.choices[0].message.tool_calls is None

    @pytest.mark.asyncio
    async def test_structured_output_and_regular_tools_called(self, providers):
        structured_output_tool = create_structured_output_tool()
        regular_tool = create_regular_tool()
        structured_data = {"answer": "The answer is 42", "confidence": 0.95}
        search_data = {"query": "what is the meaning of life"}

        for provider in providers:
            mock_response = create_mock_completion(
                tool_calls=[
                    ChatCompletionMessageToolCall(
                        id="call_1",
                        type="function",
                        function=Function(
                            name="search",
                            arguments=json.dumps(search_data),
                        ),
                    ),
                    ChatCompletionMessageToolCall(
                        id="call_2",
                        type="function",
                        function=Function(
                            name="structured_output",
                            arguments=json.dumps(structured_data),
                        ),
                    ),
                ]
            )

            with patch.object(
                provider, "function_call_without_structured_output", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = (mock_response, 10, 20, 30)

                result, _, _, _ = await provider.function_call_with_structured_output(
                    messages=[{"role": "user", "content": "What is the answer?"}],
                    tools=[regular_tool],
                    tool_choice="required",
                    structured_output_tool=structured_output_tool,
                    temperature=0.7,
                    stream=False,
                )

                assert result.choices[0].message.tool_calls is not None
                assert len(result.choices[0].message.tool_calls) == 1
                assert result.choices[0].message.tool_calls[0].function.name == "search"
                assert result.choices[0].message.content is None

    @pytest.mark.asyncio
    async def test_only_regular_tools_called(self, providers):
        structured_output_tool = create_structured_output_tool()
        regular_tool = create_regular_tool()
        search_data = {"query": "what is the meaning of life"}

        for provider in providers:
            mock_response = create_mock_completion(
                tool_calls=[
                    ChatCompletionMessageToolCall(
                        id="call_1",
                        type="function",
                        function=Function(
                            name="search",
                            arguments=json.dumps(search_data),
                        ),
                    ),
                ]
            )

            with patch.object(
                provider, "function_call_without_structured_output", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = (mock_response, 10, 20, 30)

                result, _, _, _ = await provider.function_call_with_structured_output(
                    messages=[{"role": "user", "content": "What is the answer?"}],
                    tools=[regular_tool],
                    tool_choice="required",
                    structured_output_tool=structured_output_tool,
                    temperature=0.7,
                    stream=False,
                )

                assert result.choices[0].message.tool_calls is not None
                assert len(result.choices[0].message.tool_calls) == 1
                assert result.choices[0].message.tool_calls[0].function.name == "search"
                assert result.choices[0].message.content is None

    @pytest.mark.asyncio
    async def test_no_tools_called_raises_error(self, providers):
        structured_output_tool = create_structured_output_tool()
        regular_tool = create_regular_tool()

        for provider in providers:
            mock_response = create_mock_completion(
                content="I cannot call any tools right now.",
                tool_calls=None,
            )

            with patch.object(
                provider, "function_call_without_structured_output", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = (mock_response, 10, 20, 30)

                with pytest.raises(ValueError, match="No tools were called despite tool_choice='required'"):
                    await provider.function_call_with_structured_output(
                        messages=[{"role": "user", "content": "What is the answer?"}],
                        tools=[regular_tool],
                        tool_choice="required",
                        structured_output_tool=structured_output_tool,
                        temperature=0.7,
                        stream=False,
                    )

    @pytest.mark.asyncio
    async def test_multiple_structured_output_calls_only_first_used(self, providers):
        structured_output_tool = create_structured_output_tool()
        regular_tool = create_regular_tool()
        structured_data_1 = {"answer": "First answer", "confidence": 0.95}
        structured_data_2 = {"answer": "Second answer", "confidence": 0.85}

        for provider in providers:
            mock_response = create_mock_completion(
                tool_calls=[
                    ChatCompletionMessageToolCall(
                        id="call_1",
                        type="function",
                        function=Function(
                            name="structured_output",
                            arguments=json.dumps(structured_data_1),
                        ),
                    ),
                    ChatCompletionMessageToolCall(
                        id="call_2",
                        type="function",
                        function=Function(
                            name="structured_output",
                            arguments=json.dumps(structured_data_2),
                        ),
                    ),
                ]
            )

            with patch.object(
                provider, "function_call_without_structured_output", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = (mock_response, 10, 20, 30)

                result, _, _, _ = await provider.function_call_with_structured_output(
                    messages=[{"role": "user", "content": "What is the answer?"}],
                    tools=[regular_tool],
                    tool_choice="required",
                    structured_output_tool=structured_output_tool,
                    temperature=0.7,
                    stream=False,
                )

                assert result.choices[0].message.content == json.dumps(structured_data_1, ensure_ascii=False)
                assert result.choices[0].message.tool_calls is None

    @pytest.mark.asyncio
    async def test_structured_output_with_regular_tools_filters_structured(self, providers):
        structured_output_tool = create_structured_output_tool()
        regular_tool_1 = create_regular_tool()
        regular_tool_2 = {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Calculate something",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"},
                    },
                    "required": ["expression"],
                },
            },
        }
        structured_data = {"answer": "The answer is 42", "confidence": 0.95}
        search_data = {"query": "what is the meaning of life"}
        calc_data = {"expression": "6 * 7"}

        for provider in providers:
            mock_response = create_mock_completion(
                tool_calls=[
                    ChatCompletionMessageToolCall(
                        id="call_1",
                        type="function",
                        function=Function(
                            name="search",
                            arguments=json.dumps(search_data),
                        ),
                    ),
                    ChatCompletionMessageToolCall(
                        id="call_2",
                        type="function",
                        function=Function(
                            name="structured_output",
                            arguments=json.dumps(structured_data),
                        ),
                    ),
                    ChatCompletionMessageToolCall(
                        id="call_3",
                        type="function",
                        function=Function(
                            name="calculate",
                            arguments=json.dumps(calc_data),
                        ),
                    ),
                ]
            )

            with patch.object(
                provider, "function_call_without_structured_output", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = (mock_response, 10, 20, 30)

                result, _, _, _ = await provider.function_call_with_structured_output(
                    messages=[{"role": "user", "content": "What is the answer?"}],
                    tools=[regular_tool_1, regular_tool_2],
                    tool_choice="required",
                    structured_output_tool=structured_output_tool,
                    temperature=0.7,
                    stream=False,
                )

                assert result.choices[0].message.tool_calls is not None
                assert len(result.choices[0].message.tool_calls) == 2
                tool_names = [call.function.name for call in result.choices[0].message.tool_calls]
                assert "search" in tool_names
                assert "calculate" in tool_names
                assert "structured_output" not in tool_names
                assert result.choices[0].message.content is None
