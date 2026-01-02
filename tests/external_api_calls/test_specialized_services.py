from unittest.mock import MagicMock

import pytest

from engine.llm_services.llm_service import EmbeddingService, OCRService, WebSearchService

from .capability_matrix import get_provider_model_pairs, get_provider_required_settings
from .test_helpers import mistral_ocr_messages, skip_if_missing_settings


class TestSpecializedServices:
    @pytest.mark.parametrize(
        "provider,model",
        get_provider_model_pairs("specialized", "embedding"),
        ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
    )
    def test_embedding_service(self, provider: str, model: str) -> None:
        skip_if_missing_settings(*get_provider_required_settings(provider))
        service = EmbeddingService(trace_manager=MagicMock(), provider=provider, model_name=model, embedding_size=1536)
        response = service.embed_text("hello")
        assert isinstance(response, list)
        assert len(response) > 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,model",
        get_provider_model_pairs("specialized", "embedding_async"),
        ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
    )
    async def test_embedding_service_async_returns_objects_with_embedding_attribute(
        self, provider: str, model: str
    ) -> None:
        skip_if_missing_settings(*get_provider_required_settings(provider))
        service = EmbeddingService(
            trace_manager=MagicMock(),
            provider=provider,
            model_name=model,
            embedding_size=1536,
        )

        texts = ["hello world", "test embedding"]
        result = await service.embed_text_async(texts)

        assert isinstance(result, list)
        assert len(result) == 2

        for item in result:
            assert hasattr(item, "embedding"), "Result must have .embedding attribute for qdrant compatibility"
            assert isinstance(item.embedding, list), "Embedding should be a list of floats"
            assert len(item.embedding) > 0, "Embedding should not be empty"
            assert isinstance(item.embedding[0], (int, float)), "Embedding values should be numeric"

    @pytest.mark.parametrize(
        "provider,model",
        get_provider_model_pairs("specialized", "ocr"),
        ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
    )
    def test_ocr_service(self, provider: str, model: str) -> None:
        skip_if_missing_settings(*get_provider_required_settings(provider))
        service = OCRService(trace_manager=MagicMock(), provider=provider, model_name=model)
        payload, _url_kind = mistral_ocr_messages()
        if payload is None:
            pytest.skip("Set EXTERNAL_TEST_MISTRAL_OCR_IMAGE_URL to a reachable image URL to run OCR tests.")
        response = service.get_ocr_text(payload)  # type: ignore[arg-type]
        assert isinstance(response, str)
        assert response.strip() != ""

    @pytest.mark.parametrize(
        "provider,model",
        get_provider_model_pairs("specialized", "web_search"),
        ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
    )
    def test_web_search_service(self, provider: str, model: str) -> None:
        skip_if_missing_settings(*get_provider_required_settings(provider))
        service = WebSearchService(
            trace_manager=MagicMock(),
            provider=provider,
            model_name=model,
        )
        response = service.web_search("What is the capital of France?")
        assert isinstance(response, str)
        assert response.strip() != ""
