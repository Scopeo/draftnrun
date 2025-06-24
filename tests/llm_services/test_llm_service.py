from unittest.mock import MagicMock
import json
from pydantic import BaseModel

from engine.llm_services.llm_service import CompletionService, EmbeddingService
from engine.llm_services.constrained_output_models import OutputFormatModel


class ResponseFormat(BaseModel):
    response: str
    is_successful: bool


def test_completion_service():
    completion_service = CompletionService(trace_manager=MagicMock(), provider="openai", model_name="gpt-4.1-mini")
    assert completion_service._provider == "openai"
    assert completion_service._model_name == "gpt-4.1-mini"
    assert completion_service._api_key is None
    assert completion_service._temperature == 0.5
    assert completion_service._trace_manager is not None
    text = "Hello, world!"
    response = completion_service.complete(text)
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0


def test_completion_service_constrained_complete():
    completion_service = CompletionService(trace_manager=MagicMock(), provider="openai", model_name="gpt-4.1-mini")
    text = "Hello, world!"

    response = completion_service.constrained_complete_with_pydantic(text, ResponseFormat)
    assert response is not None
    assert isinstance(response, ResponseFormat)
    assert len(response.response) > 0
    assert response.is_successful
    response_json = {
        "name": "test_response",
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    }
    assert OutputFormatModel.model_validate(response_json) is not None
    response = completion_service.constrained_complete_with_json_schema(text, json.dumps(response_json))
    print("herre")
    print(response)
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0


def test_embedding_service():
    embedding_service = EmbeddingService(
        trace_manager=MagicMock(), provider="openai", model_name="text-embedding-3-large"
    )
    assert embedding_service._provider == "openai"
    assert embedding_service._model_name == "text-embedding-3-large"
    assert embedding_service._api_key is None
    assert embedding_service._trace_manager is not None
    text = "Hello, world!"
    response = embedding_service.embed_text(text)
    assert response is not None
    assert isinstance(response, list)
    assert len(response) > 0
