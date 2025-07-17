import pytest
import base64
from unittest.mock import MagicMock

from engine.agent.llm_call_agent import LLMCallAgent
from engine.agent.utils import load_str_to_json
from engine.agent.agent import AgentPayload, ComponentAttributes
from engine.llm_services.utils import chat_completion_to_response


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
    tool_description = MagicMock()
    component_attributes = ComponentAttributes(
        component_instance_name="test_component", component_instance_id="test_instance_id"
    )
    prompt_template = "{input}"
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
    )
    return agent


@pytest.mark.anyio
async def test_agent_input_combinations(llm_call_with_output_format, input_payload):
    response = await llm_call_with_output_format._run_without_trace(input_payload)

    # Check that the question was passed in the messages
    assert isinstance(response, AgentPayload)

    # Check that response_format was passed
    response_format = llm_call_with_output_format.output_format
    assert response_format is not None
    assert response_format["name"] == "weather_data"
    assert response_format["type"] == "json_schema"
    assert isinstance(response_format["strict"], bool) and response_format["strict"] is True


@pytest.mark.anyio
async def test_chat_completion_to_response(llm_call_with_output_format, input_payload_with_file):
    response = await llm_call_with_output_format._run_without_trace(input_payload_with_file)
    # Check that the question was passed in the messages
    assert isinstance(response, AgentPayload)

    llm_service_input_messages = (
        llm_call_with_output_format._completion_service.constrained_complete_with_json_schema.call_args[1]["messages"]
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
