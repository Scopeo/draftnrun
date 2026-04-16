import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.components.llm_call import _convert_properties_to_openai_format
from engine.components.scorer import OUTPUT_FORMAT, Scorer, ScorerInputs
from engine.components.types import ComponentAttributes
from engine.llm_services.constrained_output_models import OutputFormatModel
from tests.components.test_llm_call import make_capability_resolver


@pytest.fixture
def mock_completion_service():
    service = MagicMock()
    service._provider = "openai"
    service._model_name = "gpt-4.1-mini"
    service._model_id = None
    service._invocation_parameters = {}
    service.constrained_complete_with_json_schema_async = AsyncMock(
        return_value=json.dumps({"score": 85, "reason": "Clear and well-structured"})
    )
    return service


@pytest.fixture
def scorer(mock_completion_service):
    trace_manager = MagicMock()
    return Scorer(
        completion_service=mock_completion_service,
        trace_manager=trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_scorer"),
        capability_resolver=make_capability_resolver(mock_completion_service),
    )


class TestScorerOutputFormat:
    def test_output_format_is_flat_properties(self):
        assert "name" not in OUTPUT_FORMAT
        assert "strict" not in OUTPUT_FORMAT
        assert "schema" not in OUTPUT_FORMAT
        assert "score" in OUTPUT_FORMAT
        assert "reason" in OUTPUT_FORMAT

    def test_output_format_passes_openai_conversion_and_validation(self):
        openai_format = _convert_properties_to_openai_format(OUTPUT_FORMAT)
        openai_format["strict"] = True
        openai_format["type"] = "json_schema"
        OutputFormatModel(**openai_format)


@pytest.mark.anyio
async def test_scorer_run(scorer, mock_completion_service):
    inputs = ScorerInputs(input="The sky is blue.", criteria="Factual accuracy")
    outputs = await scorer._run_without_io_trace(inputs, ctx={})

    assert outputs.score == 85
    assert outputs.reason == "Clear and well-structured"
    assert json.loads(outputs.output) == {"score": 85, "reason": "Clear and well-structured"}
    mock_completion_service.constrained_complete_with_json_schema_async.assert_awaited_once()


@pytest.mark.anyio
async def test_scorer_run_with_additional_context(scorer, mock_completion_service):
    inputs = ScorerInputs(
        input="The sky is blue.",
        criteria="Factual accuracy",
        additional_context="Scientific context expected",
    )
    outputs = await scorer._run_without_io_trace(inputs, ctx={})

    assert outputs.score == 85
    mock_completion_service.constrained_complete_with_json_schema_async.assert_awaited_once()
