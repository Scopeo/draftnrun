import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.components.categorizer import Categorizer, CategorizerInputs, _build_output_format
from engine.components.llm_call import _convert_properties_to_openai_format
from engine.components.types import ComponentAttributes
from engine.llm_services.constrained_output_models import OutputFormatModel
from tests.components.test_llm_call import make_capability_resolver

CATEGORIES = {
    "Positive": "Content expressing positive sentiment",
    "Negative": "Content expressing negative sentiment",
    "Neutral": "Content with neutral sentiment",
}


@pytest.fixture
def mock_completion_service():
    service = MagicMock()
    service._provider = "openai"
    service._model_name = "gpt-4.1-mini"
    service._model_id = None
    service._invocation_parameters = {}
    service.constrained_complete_with_json_schema_async = AsyncMock(
        return_value=json.dumps({"category": "Positive", "score": 0.95, "reason": "Upbeat tone"})
    )
    return service


@pytest.fixture
def categorizer(mock_completion_service, monkeypatch):
    monkeypatch.setattr(
        "engine.components.llm_call.CompletionService", MagicMock(return_value=mock_completion_service)
    )
    trace_manager = MagicMock()
    return Categorizer(
        trace_manager=trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_categorizer"),
        capability_resolver=make_capability_resolver(mock_completion_service),
    )


class TestCategorizerOutputFormat:
    def test_output_format_is_flat_properties(self):
        raw = json.loads(_build_output_format(CATEGORIES))
        assert "name" not in raw
        assert "strict" not in raw
        assert "schema" not in raw
        assert "category" in raw
        assert "score" in raw
        assert "reason" in raw

    def test_output_format_passes_openai_conversion_and_validation(self):
        raw = json.loads(_build_output_format(CATEGORIES))
        openai_format = _convert_properties_to_openai_format(raw)
        openai_format["strict"] = True
        openai_format["type"] = "json_schema"
        OutputFormatModel(**openai_format)

    def test_category_enum_matches_input(self):
        raw = json.loads(_build_output_format(CATEGORIES))
        assert raw["category"]["enum"] == list(CATEGORIES.keys())


@pytest.mark.anyio
async def test_categorizer_run(categorizer, mock_completion_service):
    inputs = CategorizerInputs(
        content_to_categorize="I love this product!",
        categories=CATEGORIES,
    )
    outputs = await categorizer._run_without_io_trace(inputs, ctx={})

    assert outputs.category == "Positive"
    assert outputs.score == 0.95
    assert outputs.reason == "Upbeat tone"
    assert json.loads(outputs.output) == {"category": "Positive", "score": 0.95, "reason": "Upbeat tone"}
    mock_completion_service.constrained_complete_with_json_schema_async.assert_awaited_once()


@pytest.mark.anyio
async def test_categorizer_run_with_additional_context(categorizer, mock_completion_service):
    inputs = CategorizerInputs(
        content_to_categorize="I love this product!",
        categories=CATEGORIES,
        additional_context="Focus on emotional language",
    )
    outputs = await categorizer._run_without_io_trace(inputs, ctx={})

    assert outputs.category == "Positive"
    mock_completion_service.constrained_complete_with_json_schema_async.assert_awaited_once()
