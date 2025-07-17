import pytest
import base64
import asyncio
from unittest.mock import MagicMock

from engine.agent.agent import ComponentAttributes
from engine.agent.llm_call_agent import LLMCallAgent

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


def complete_side_effect(**kwargs):
    return kwargs["messages"][0]["content"]


@pytest.fixture
def llm_call_with_file_content():
    trace_manager = MagicMock()
    llm_service = MagicMock()
    # Mock complete to return the input text content as response
    llm_service.complete.side_effect = complete_side_effect
    tool_description = MagicMock()
    component_attributes = ComponentAttributes(
        component_name="test_component", component_instance_id="test_instance_id"
    )
    prompt_template = "{input}"
    file_content = "{file}"
    return LLMCallAgent(
        trace_manager,
        llm_service,
        tool_description,
        component_attributes,
        prompt_template,
        file_content=file_content,
    )


@pytest.fixture
def llm_call_without_file_content():
    trace_manager = MagicMock()
    llm_service = MagicMock()
    # Mock complete to return the input text content as response
    llm_service.complete.side_effect = complete_side_effect
    tool_description = MagicMock()
    component_attributes = ComponentAttributes(
        component_name="test_component", component_instance_id="test_instance_id"
    )
    prompt_template = "{input}"
    return LLMCallAgent(trace_manager, llm_service, tool_description, component_attributes, prompt_template)


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

    response = asyncio.run(agent_instance._run_without_trace(payload_instance))

    assert QUESTION in response.messages[0].content or QUESTION in response.messages[0].content[0]["text"]
    if isinstance(response.messages[0].content, list):
        if expected_file:
            assert expected_file == response.messages[0].content[1]["file"]["filename"]
    else:
        assert isinstance(response.messages[0].content, str) or (
            isinstance(response.messages[0].content, list) and len(response.messages[0].content) == 1
        )
