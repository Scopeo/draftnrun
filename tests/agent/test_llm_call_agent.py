import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.agent.agent import ComponentAttributes
from engine.agent.llm_call_agent import LLMCallAgent, LLMCallInputs


def make_capability_resolver(service, default_capabilities=None):
    def resolver(capabilities):
        provider = getattr(service, "_provider", None)
        model = getattr(service, "_model_name", None)
        refs = set(default_capabilities) if default_capabilities else set()
        if provider and model:
            refs.add(f"{provider}:{model}")
        return refs

    return resolver


FILE_PATH_1 = "file_1.pdf"
FILE_PATH_2 = "file_2.pdf"
QUESTION = "What is the content of the file?"
base64_string = base64.b64encode(b"dummy pdf content").decode("utf-8")


@pytest.fixture
def input_payload_format_file_as_message():
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": FILE_PATH_1,
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
def input_payload_format_file_as_independant_key():
    return {
        "messages": [
            {
                "role": "user",
                "content": QUESTION,
            },
        ],
        "file": {
            "filename": FILE_PATH_1,
            "file_data": f"data:application/pdf;base64,{base64_string}",
        },
    }


@pytest.fixture
def input_payload_format_file_as_both_message_and_independant_key():
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": FILE_PATH_1,
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
        "file": {
            "filename": FILE_PATH_2,
            "file_data": f"data:application/pdf;base64,{base64_string}",
        },
    }


@pytest.fixture
def input_payload_format_no_file():
    return {
        "messages": [
            {
                "role": "user",
                "content": QUESTION,
            },
        ],
    }


async def complete_side_effect(**kwargs):
    content = kwargs["messages"][0]["content"]
    # If content is a list (with files), extract the text part
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item["text"]
        return "What is the content of the file?"  # fallback
    return content


@pytest.fixture
def llm_call_with_file_content():
    trace_manager = MagicMock()
    llm_service = MagicMock()
    llm_service._provider = "openai"  # Set the provider to openai to support file content
    llm_service._model_name = "gpt-4.1-mini"  # Set a model that supports files

    # Use AsyncMock for the async methods
    llm_service.complete_async = AsyncMock(side_effect=complete_side_effect)
    llm_service.constrained_complete_with_json_schema_async = AsyncMock(side_effect=complete_side_effect)

    tool_description = MagicMock()
    component_attributes = ComponentAttributes(
        component_instance_name="test_component",
    )
    prompt_template = "{{input}}"
    file_content = "{file}"
    return LLMCallAgent(
        trace_manager,
        llm_service,
        tool_description,
        component_attributes,
        prompt_template,
        file_content_key=file_content,
        capability_resolver=make_capability_resolver(llm_service),
    )


@pytest.fixture
def llm_call_without_file_content():
    trace_manager = MagicMock()
    llm_service = MagicMock()
    llm_service._provider = "openai"  # Set the provider to openai to support file content
    llm_service._model_name = "gpt-4.1-mini"  # Set a model that supports files

    # Use AsyncMock for the async methods
    llm_service.complete_async = AsyncMock(side_effect=complete_side_effect)
    llm_service.constrained_complete_with_json_schema_async = AsyncMock(side_effect=complete_side_effect)

    tool_description = MagicMock()
    component_attributes = ComponentAttributes(component_instance_name="test_component")
    prompt_template = "{{input}}"
    return LLMCallAgent(
        trace_manager,
        llm_service,
        tool_description,
        component_attributes,
        prompt_template,
        capability_resolver=make_capability_resolver(llm_service),
    )


@pytest.mark.parametrize(
    "agent,input_payload,expected_file",
    [
        ("llm_call_with_file_content", "input_payload_format_no_file", None),
        ("llm_call_with_file_content", "input_payload_format_file_as_message", FILE_PATH_1),
        ("llm_call_with_file_content", "input_payload_format_file_as_independant_key", FILE_PATH_1),
        ("llm_call_with_file_content", "input_payload_format_file_as_both_message_and_independant_key", FILE_PATH_1),
        ("llm_call_without_file_content", "input_payload_format_no_file", None),
        ("llm_call_without_file_content", "input_payload_format_file_as_message", FILE_PATH_1),
        ("llm_call_without_file_content", "input_payload_format_file_as_independant_key", FILE_PATH_1),
        (
            "llm_call_without_file_content",
            "input_payload_format_file_as_both_message_and_independant_key",
            FILE_PATH_1,
        ),
    ],
)
def test_agent_input_combinations(agent, input_payload, expected_file, request):
    agent_instance = request.getfixturevalue(agent)
    payload_instance = request.getfixturevalue(input_payload)

    # Convert dict to LLMCallInputs Pydantic model
    inputs = LLMCallInputs.model_validate(payload_instance)

    response = asyncio.run(agent_instance._run_without_io_trace(inputs, ctx={}))

    # Check that the response contains the expected output
    assert isinstance(response.output, str)
    assert QUESTION in response.output
