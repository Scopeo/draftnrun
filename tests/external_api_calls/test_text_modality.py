from unittest.mock import MagicMock

import pytest

from engine.agent.types import ToolDescription
from engine.llm_services.llm_service import CompletionService

from .capability_matrix import get_provider_model_pairs, get_provider_required_settings
from .test_helpers import (
    ConstrainedResponse,
    default_tool_description,
    json_schema_str,
    parse_possibly_double_encoded_json,
    skip_if_missing_settings,
)


class TestTextModality:
    class TestComplete:
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "complete"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        def test_basic_completion(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            prompt = "Say 'ok' and nothing else."
            messages: list[dict] | str
            if provider == "openai":
                messages = prompt
            else:
                messages = [{"role": "user", "content": prompt}]
            response = service.complete(messages)
            assert isinstance(response, str)
            assert response.strip() != ""

        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "complete_structured_pydantic"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        def test_structured_output_pydantic(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            response = service.constrained_complete_with_pydantic(
                "Return JSON with response='ok' and is_successful=true.", ConstrainedResponse
            )
            assert isinstance(response, ConstrainedResponse)
            assert isinstance(response.response, str)
            assert response.response.strip() != ""
            assert response.is_successful is True

        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "complete_structured_json_schema"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        def test_structured_output_json_schema(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            raw = service.constrained_complete_with_json_schema("Return JSON with key 'text'.", json_schema_str())
            assert isinstance(raw, str)
            assert raw.strip() != ""
            parsed = parse_possibly_double_encoded_json(raw)
            assert isinstance(parsed, dict)
            assert "text" in parsed

    class TestFunctionCall:
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "function_call"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        def test_basic_function_call(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            tool = default_tool_description()
            messages = [{"role": "user", "content": "Call the tool extract_answer with answer='ok' and ok=true."}]
            response = service.function_call(messages=messages, tools=[tool], tool_choice="required")
            assert response is not None
            assert len(response.choices) == 1
            assert response.choices[0].message is not None

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "function_call_structured"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        async def test_function_call_with_structured_output(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            structured_tool = default_tool_description()
            messages = [{"role": "user", "content": "Return answer='ok' and ok=true using the extract_answer tool."}]
            response = await service.function_call_async(
                messages=messages,
                tools=[],
                tool_choice="required",
                structured_output_tool=structured_tool,
            )
            content = response.choices[0].message.content
            assert isinstance(content, str) and content.strip(), (
                "Expected structured output in message.content as a JSON string"
            )
            parsed = parse_possibly_double_encoded_json(content)
            assert parsed.get("answer"), f"Provider {provider} returned structured output without 'answer' field"
            assert parsed.get("ok") is True, f"Provider {provider} returned structured output with ok != True"

        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "function_call_with_system"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        def test_function_call_with_system_message(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            tool = default_tool_description()
            messages = [
                {"role": "system", "content": "You are a helpful assistant that calls tools when requested."},
                {"role": "user", "content": "Call the tool extract_answer with answer='ok' and ok=true."},
            ]
            response = service.function_call(messages=messages, tools=[tool], tool_choice="required")
            assert response is not None
            assert len(response.choices) == 1
            assert response.choices[0].message is not None

        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "function_call_empty_tools"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        def test_function_call_with_empty_tools(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            messages = [{"role": "user", "content": "Say 'ok' and nothing else."}]
            response = service.function_call(messages=messages, tools=[], tool_choice="auto")
            assert response is not None
            assert len(response.choices) == 1
            assert response.choices[0].message is not None
            assert response.choices[0].message.content is not None

        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "function_call_tool_choice_none"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        def test_function_call_with_tool_choice_none(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            tool = default_tool_description()
            messages = [{"role": "user", "content": "Say 'ok' and nothing else."}]
            response = service.function_call(messages=messages, tools=[tool], tool_choice="none")
            assert response is not None
            assert len(response.choices) == 1
            assert response.choices[0].message is not None
            # Should have content (simple completion), not tool calls
            assert response.choices[0].message.content is not None
            assert response.choices[0].message.tool_calls is None

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "function_call_tool_choice_none"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        async def test_function_call_structured_with_tool_choice_none(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)
            structured_tool = default_tool_description()
            regular_tool = ToolDescription(
                name="other_tool",
                description="Some other tool",
                tool_properties={"value": {"type": "string"}},
                required_tool_properties=["value"],
            )
            messages = [{"role": "user", "content": "Return answer='ok' and ok=true using extract_answer format."}]
            response = await service.function_call_async(
                messages=messages,
                tools=[regular_tool],
                tool_choice="none",
                structured_output_tool=structured_tool,
            )
            content = response.choices[0].message.content
            assert isinstance(content, str) and content.strip(), (
                "Expected structured output in message.content as a JSON string"
            )
            parsed = parse_possibly_double_encoded_json(content)
            assert parsed.get("answer"), f"Provider {provider} returned output without 'answer' field: {parsed}"
            assert parsed.get("ok") is True, f"Provider {provider} returned output with ok != True: {parsed}"

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "function_call_multi_turn"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        async def test_multi_turn_function_calling_with_tool_responses(self, provider: str, model: str) -> None:
            """
            Test multi-turn conversation with tool execution.
            Ensures tool response messages are properly converted for each provider's format.
            - Anthropic: needs tool results as user messages with tool_result blocks
            - OpenAI/Others: should handle tool role messages correctly
            """
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)

            tool = ToolDescription(
                name="get_weather",
                description="Get weather information",
                tool_properties={"city": {"type": "string", "description": "City name"}},
                required_tool_properties=["city"],
            )

            # First turn: user asks, assistant calls tool
            messages = [{"role": "user", "content": "What's the weather in Paris?"}]
            response1 = await service.function_call_async(messages=messages, tools=[tool], tool_choice="auto")

            # Verify tool was called
            assert response1.choices[0].message.tool_calls is not None
            assert len(response1.choices[0].message.tool_calls) > 0
            tool_call = response1.choices[0].message.tool_calls[0]

            # Second turn: add tool response
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                    }
                ],
            })
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": "Weather in Paris: Sunny, 22°C"})

            # This should not fail - Anthropic provider must convert 'tool' role properly
            response2 = await service.function_call_async(messages=messages, tools=[tool], tool_choice="auto")
            assert response2 is not None
            assert response2.choices[0].message.content is not None

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("text", "function_call_both_tools_and_structured"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        async def test_function_call_with_both_regular_and_structured_tools(self, provider: str, model: str) -> None:
            """
            Test function calling with both regular tools AND structured output tool.
            Catches the bug where structured output tool would be executed as a regular tool.
            """
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)

            # Regular tool
            calculator_tool = ToolDescription(
                name="calculate",
                description="Perform calculation",
                tool_properties={"expression": {"type": "string", "description": "Math expression"}},
                required_tool_properties=["expression"],
            )

            # Structured output tool
            structured_tool = ToolDescription(
                name="format_response",
                description="Format the final response",
                tool_properties={
                    "answer": {"type": "string", "description": "The answer"},
                    "confidence": {"type": "number", "description": "Confidence 0-1"},
                },
                required_tool_properties=["answer", "confidence"],
            )

            messages = [{"role": "user", "content": "Tell me with confidence: what is 2+2?"}]
            response = await service.function_call_async(
                messages=messages,
                tools=[calculator_tool],
                tool_choice="auto",
                structured_output_tool=structured_tool,
            )

            # Response should either call a tool or have content
            assert response is not None
            msg = response.choices[0].message
            assert msg.tool_calls is not None or msg.content is not None
