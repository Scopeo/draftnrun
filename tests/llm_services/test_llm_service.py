import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from engine.llm_services.constrained_output_models import OutputFormatModel
from engine.llm_services.llm_service import DEFAULT_TEMPERATURE, CompletionService, EmbeddingService
from engine.trace.span_context import set_tracing_span


class ResponseFormat(BaseModel):
    response: str
    is_successful: bool


@pytest.fixture(autouse=True)
def setup_tracing_context():
    """Set up tracing context for all tests in this module."""
    set_tracing_span(
        project_id="test-project",
        organization_id="test-org",
        organization_llm_providers=["openai", "mistral", "google", "cohere"],
        conversation_id="test-conversation",
    )


def test_completion_service():
    completion_service = CompletionService(trace_manager=MagicMock(), provider="openai", model_name="gpt-4.1-mini")
    assert completion_service._provider == "openai"
    assert completion_service._model_name == "gpt-4.1-mini"
    assert completion_service._api_key is not None
    assert completion_service._invocation_parameters.get("temperature") == DEFAULT_TEMPERATURE
    assert completion_service._trace_manager is not None
    text = "Hello, world!"
    response = completion_service.complete(text)
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_completion_service_async():
    completion_service = CompletionService(trace_manager=MagicMock(), provider="openai", model_name="gpt-4o-mini")
    assert completion_service._provider == "openai"
    assert completion_service._model_name == "gpt-4o-mini"
    assert completion_service._api_key is not None
    assert completion_service._invocation_parameters.get("temperature") == DEFAULT_TEMPERATURE
    assert completion_service._trace_manager is not None
    text = "Hello, world!"
    response = await completion_service.complete_async(text)
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
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_completion_service_constrained_complete_async():
    completion_service = CompletionService(trace_manager=MagicMock(), provider="openai", model_name="gpt-4.1-mini")
    text = "Hello, world!"

    response = await completion_service.constrained_complete_with_pydantic_async(text, ResponseFormat)
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
    response = await completion_service.constrained_complete_with_json_schema_async(text, json.dumps(response_json))
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0


def test_embedding_service():
    embedding_service = EmbeddingService(
        trace_manager=MagicMock(), provider="openai", model_name="text-embedding-3-large"
    )
    assert embedding_service._provider == "openai"
    assert embedding_service._model_name == "text-embedding-3-large"
    assert embedding_service._api_key is not None
    assert embedding_service._trace_manager is not None
    text = "Hello, world!"
    response = embedding_service.embed_text(text)
    assert response is not None
    assert isinstance(response, list)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_embedding_service_async():
    embedding_service = EmbeddingService(
        trace_manager=MagicMock(), provider="openai", model_name="text-embedding-3-large"
    )
    assert embedding_service._provider == "openai"
    assert embedding_service._model_name == "text-embedding-3-large"
    assert embedding_service._api_key is not None
    assert embedding_service._trace_manager is not None
    text = "Hello, world!"
    response = await embedding_service.embed_text_async(text)
    assert response is not None
    assert isinstance(response, list)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_custom_provider_constrained_output():
    """Test that custom providers work with constrained output methods and handle errors."""
    with (
        patch("engine.llm_services.providers.provider_factory.settings") as mock_settings,
    ):
        mock_settings.custom_models = {
            "custom_models": {
                "dummy-provider": [
                    {
                        "model_name": "dummy-model",
                        "api_key": "dummy-api-key",
                        "base_url": "https://dummy-api.com/v1",
                    }
                ]
            }
        }

        completion_service = CompletionService(
            trace_manager=MagicMock(), provider="dummy-provider", model_name="dummy-model"
        )

        assert completion_service._provider == "dummy-provider"
        assert completion_service._api_key == "dummy-api-key"
        assert completion_service._base_url == "https://dummy-api.com/v1"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"response": "Test response", "is_successful": true}'
        mock_response.usage = MagicMock()
        mock_response.usage.completion_tokens = 10
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.total_tokens = 15

        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            response = await completion_service.constrained_complete_with_pydantic_async(
                "Test message", ResponseFormat
            )
            assert isinstance(response, ResponseFormat)
            assert response.response == "Test response"
            assert response.is_successful is True

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

            response = await completion_service.constrained_complete_with_json_schema_async(
                "Test message", json.dumps(response_json)
            )
            assert isinstance(response, str)
            assert len(response) > 0

        mock_error_response = MagicMock()
        mock_error_response.choices = [MagicMock()]
        mock_error_response.choices[0].message.content = '{"invalid": json}'  # Invalid JSON
        mock_error_response.usage = MagicMock()
        mock_error_response.usage.completion_tokens = 5
        mock_error_response.usage.prompt_tokens = 3
        mock_error_response.usage.total_tokens = 8

        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_error_response)
            mock_openai.return_value = mock_client

            with pytest.raises(ValueError, match="Error processing constrained completion.*dummy-model"):
                await completion_service.constrained_complete_with_pydantic_async("Test message", ResponseFormat)

            response_invalid = await completion_service.constrained_complete_with_json_schema_async(
                "Test message", json.dumps(response_json)
            )
            assert isinstance(response_invalid, str)
            assert len(response_invalid) > 0

        # Test error case - API exception
        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
            mock_openai.return_value = mock_client

            # Test that API errors are properly handled and re-raised with custom provider context
            with pytest.raises(ValueError, match="Error processing constrained completion.*dummy-model.*API Error"):
                await completion_service.constrained_complete_with_pydantic_async("Test message", ResponseFormat)

            with pytest.raises(ValueError, match="Error processing constrained completion.*dummy-model.*API Error"):
                await completion_service.constrained_complete_with_json_schema_async(
                    "Test message", json.dumps(response_json)
                )

        # Simple generic error smoke test: ensure try/except surfaces ValueError for both methods
        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("boom"))
            mock_openai.return_value = mock_client

            with pytest.raises(ValueError):
                await completion_service.constrained_complete_with_pydantic_async("Test message", ResponseFormat)

            with pytest.raises(ValueError):
                await completion_service.constrained_complete_with_json_schema_async(
                    "Test message", json.dumps(response_json)
                )
