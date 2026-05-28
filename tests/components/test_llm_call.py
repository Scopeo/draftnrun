import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.components.component import ComponentAttributes
from engine.components.llm_call import LLMCallAgent, LLMCallInputs


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
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item["text"]
        return "What is the content of the file?"
    return content


def _build_mock_service():
    svc = MagicMock()
    svc._provider = "openai"
    svc._model_name = "gpt-4.1-mini"
    svc._model_id = None
    svc.complete_async = AsyncMock(side_effect=complete_side_effect)
    svc.constrained_complete_with_json_schema_async = AsyncMock(side_effect=complete_side_effect)
    return svc


@pytest.fixture
def llm_call_with_file_content(monkeypatch):
    mock_service = _build_mock_service()
    monkeypatch.setattr(
        "engine.components.llm_call.CompletionService", MagicMock(return_value=mock_service)
    )
    return LLMCallAgent(
        trace_manager=MagicMock(),
        tool_description=MagicMock(),
        component_attributes=ComponentAttributes(component_instance_name="test_component"),
        file_content_key="{file}",
        capability_resolver=make_capability_resolver(mock_service),
    )


@pytest.fixture
def llm_call_without_file_content(monkeypatch):
    mock_service = _build_mock_service()
    monkeypatch.setattr(
        "engine.components.llm_call.CompletionService", MagicMock(return_value=mock_service)
    )
    return LLMCallAgent(
        trace_manager=MagicMock(),
        tool_description=MagicMock(),
        component_attributes=ComponentAttributes(component_instance_name="test_component"),
        capability_resolver=make_capability_resolver(mock_service),
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

    inputs = LLMCallInputs.model_validate({**payload_instance, "prompt_template": "{{input}}"})

    response = asyncio.run(agent_instance._run_without_io_trace(inputs, ctx={}))

    assert isinstance(response.output, str)
    assert QUESTION in response.output
