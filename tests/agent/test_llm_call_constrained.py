import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.agent.llm_call_agent import LLMCallAgent, LLMCallInputs
from engine.agent.utils import load_str_to_json
from engine.agent.types import ComponentAttributes
from engine.llm_services.utils import chat_completion_to_response
from tests.agent.test_llm_call_agent import make_capability_resolver


base64_string = base64.b64encode(b"dummy pdf content").decode("utf-8")
QUESTION = "What is the ideal weather for a pool party?"


@pytest.fixture
def input_payload():
    return {
        "messages": [
            {
                "role": "user",
                "content": QUESTION,
            },
        ],
    }


@pytest.fixture
def input_payload_with_file():
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": "weather_data.pdf",
                            "file_data": f"data:application/pdf;base64,{base64_string}",
                        },
                    },
                    {
                        "type": "text",
                        "text": QUESTION,
                    },
                ],
            },
        ],
    }


@pytest.fixture
def llm_call_with_output_format():
    trace_manager = MagicMock()

    llm_service = MagicMock()
    llm_service._provider = "openai"  # Set the provider to openai to support file content
    llm_service._model_name = "gpt-4.1-mini"  # Set a model that supports files
    llm_service.constrained_complete_with_json_schema_async = AsyncMock(
        return_value='{"location": "Miami", "unit": "F", "value": 85}'
    )
    llm_service.complete_async = AsyncMock(return_value="Sample response")

    tool_description = MagicMock()
    component_attributes = ComponentAttributes(
        component_instance_name="test_component",
    )
    prompt_template = "{{input}}"
    output_format = load_str_to_json(
        """{
        "name": "weather_data",
        "type": "json_schema",
        "strict": true,
        "schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location to get the weather for"
                },
                "unit": {
                    "type": ["string", "null"],
                    "description": "The unit to return the temperature in",
                    "enum": ["F", "C"]
                },
                "value": {
                    "type": "number",
                    "description": "The actual temperature value in the location",
                    "minimum": -130,
                    "maximum": 130
                }
            },
            "additionalProperties": false,
            "required": [
                "location", "unit", "value"
            ]
        }
    }"""
    )
    agent = LLMCallAgent(
        trace_manager,
        llm_service,
        tool_description,
        component_attributes,
        prompt_template,
        output_format=output_format,
        capability_resolver=make_capability_resolver(llm_service),
    )
    return agent


@pytest.mark.anyio
async def test_agent_input_combinations(llm_call_with_output_format, input_payload):
    # Convert dict to LLMCallInputs Pydantic model
    inputs = LLMCallInputs.model_validate(input_payload)
    response = await llm_call_with_output_format._run_without_io_trace(inputs, ctx={})

    # Check that the response is the correct type
    assert isinstance(response.output, str)

    # Check that response_format was passed
    response_format = llm_call_with_output_format.output_format
    assert response_format is not None
    assert response_format["name"] == "weather_data"
    assert response_format["type"] == "json_schema"
    assert isinstance(response_format["strict"], bool) and response_format["strict"] is True


@pytest.mark.anyio
async def test_chat_completion_to_response(llm_call_with_output_format, input_payload_with_file):
    # Convert dict to LLMCallInputs Pydantic model
    inputs = LLMCallInputs.model_validate(input_payload_with_file)
    response = await llm_call_with_output_format._run_without_io_trace(inputs, ctx={})
    # Check that the response is the correct type
    assert isinstance(response.output, str)

    llm_service_input_messages = (
        llm_call_with_output_format._completion_service.constrained_complete_with_json_schema_async.call_args[1][
            "messages"
        ]
    )
    converted_messages = chat_completion_to_response(llm_service_input_messages)
    assert converted_messages == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": QUESTION},
                {
                    "type": "input_file",
                    "filename": "weather_data.pdf",
                    "file_data": f"data:application/pdf;base64,{base64_string}",
                },
            ],
        }
    ]
