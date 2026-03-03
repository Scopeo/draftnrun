import json
import logging
from typing import Any, Optional, Type

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field, field_validator

from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
from engine.components.component import Component
from engine.components.errors import CategorizationError
from engine.components.types import ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import CompletionService
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


DEFAULT_CATEGORIZER_TOOL_DESCRIPTION = ToolDescription(
    name="Categorizer",
    description="Categorizes content into predefined categories",
    tool_properties={
        "input": {
            "type": "string",
            "description": "The content to categorize",
        }
    },
    required_tool_properties=["input"],
)


def _build_system_prompt(categories: dict[str, str], additional_context: Optional[str] = None) -> str:
    prompt = (
        "You are a categorization assistant. Your task is to categorize the provided content "
        "into one of the predefined categories.\n\n"
    )

    if additional_context:
        prompt += f"Additional context: {additional_context}\n\n"

    prompt += "Categories:\n"
    for name, description in categories.items():
        prompt += f"- {name}: {description}\n"

    prompt += (
        "\nAnalyze the content and provide:\n"
        "1. The most appropriate category\n"
        "2. A confidence score (0-1) indicating how well the content matches the category\n"
        "3. A brief reason explaining why this category was selected"
    )

    return prompt


def _build_output_format(categories: dict[str, str]) -> dict[str, Any]:
    category_names = list(categories.keys())

    return {
        "name": "categorization_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "The selected category",
                    "enum": category_names,
                },
                "score": {
                    "type": "number",
                    "description": "Confidence score between 0 and 1",
                },
                "reason": {
                    "type": "string",
                    "description": "Brief explanation for why this category was selected",
                },
            },
            "additionalProperties": False,
            "required": ["category", "score", "reason"],
        },
    }


class CategorizerInputs(BaseModel):
    content_to_categorize: str = Field(
        default="",
        description="The content to categorize",
        json_schema_extra={
            "parameter_type": ParameterType.STRING,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Input",
                placeholder="Enter the content to categorize",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    categories: dict[str, str] = Field(
        description="Available categories with their descriptions to choose from.",
        json_schema_extra={
            "ui_component": UIComponent.CATEGORIES_BUILDER,
            "is_tool_input": False,
            "parameter_type": ParameterType.JSON,
            "ui_component_properties": UIComponentProperties(
                label="Categories",
                placeholder=(
                    "{\n"
                    '  "Positive": "Content expressing positive sentiment",\n'
                    '  "Negative": "Content expressing negative sentiment",\n'
                    '  "Neutral": "Content with neutral sentiment"\n'
                    "}"
                ),
                description="Define the categories you want to classify content into.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    additional_context: Optional[str] = Field(
        default=None,
        description="Additional information to help with categorization",
        json_schema_extra={
            "ui_component": UIComponent.TEXTAREA,
            "is_tool_input": False,
            "ui_component_properties": UIComponentProperties(
                label="Additional Context",
                placeholder="Add any additional context or instructions for categorization",
                description=(
                    "Provide extra context to improve accuracy. "
                    "For example: specific criteria to consider, edge cases to watch for, "
                    "domain-specific knowledge, or instructions on how to handle ambiguous cases."
                ),
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )

    @field_validator("categories", mode="before")
    @classmethod
    def parse_categories(cls, v):
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            if not v or v.strip() == "":
                raise ValueError("Categories cannot be empty. Provide at least one category with a description.")
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"Categories must be valid JSON: {e}") from e
            if not isinstance(parsed, dict):
                raise ValueError("Categories must be a JSON object mapping category names to descriptions.")
            if not parsed:
                raise ValueError("Categories cannot be empty. Provide at least one category with a description.")
            return parsed
        return v


class CategorizerOutputs(BaseModel):
    category: str = Field(description="The selected category")
    score: float = Field(description="Confidence score (0-1)")
    reason: str = Field(description="Explanation for the categorization")
    output: dict[str, Any] = Field(description="Full categorization result with category, score, and reason")


class Categorizer(Component):
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return CategorizerInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return CategorizerOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "content_to_categorize", "output": "output"}

    def __init__(
        self,
        completion_service: CompletionService,
        trace_manager: TraceManager,
        tool_description: ToolDescription = DEFAULT_CATEGORIZER_TOOL_DESCRIPTION,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        if component_attributes is None:
            component_attributes = ComponentAttributes(component_instance_name=self.__class__.__name__)
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._completion_service = completion_service

    async def _run_without_io_trace(
        self,
        inputs: CategorizerInputs,
        ctx: dict,
    ) -> CategorizerOutputs:
        content = inputs.content_to_categorize
        system_prompt = _build_system_prompt(inputs.categories, inputs.additional_context)
        output_format = _build_output_format(inputs.categories)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]

        span = get_current_span()
        span.set_attributes({
            SpanAttributes.INPUT_VALUE: serialize_to_json(messages, shorten_string=True),
            SpanAttributes.LLM_MODEL_NAME: self._completion_service._model_name,
            "model_id": (
                str(self._completion_service._model_id) if self._completion_service._model_id is not None else None
            ),
        })

        response = await self._completion_service.constrained_complete_with_json_schema_async(
            messages=messages,
            response_format=json.dumps(output_format),
        )

        try:
            result = json.loads(response)
        except json.JSONDecodeError as e:
            raise CategorizationError(detail=f"Failed to parse LLM output as JSON: {e}", llm_output=response)

        try:
            category = result.get("category")
            score = result.get("score")
            reason = result.get("reason")

            if not category:
                raise CategorizationError(detail="LLM response missing 'category' field", llm_output=result)
            if score is None:
                raise CategorizationError(detail="LLM response missing 'score' field", llm_output=result)
            if not reason:
                raise CategorizationError(detail="LLM response missing 'reason' field", llm_output=result)

            score = float(score)

        except (ValueError, KeyError) as e:
            raise CategorizationError(detail=f"Invalid value in LLM response: {str(e)}", llm_output=result) from e

        outputs = CategorizerOutputs(
            category=category,
            score=score,
            reason=reason,
            output={"category": category, "score": score, "reason": reason},
        )

        span.set_attribute(SpanAttributes.OUTPUT_VALUE, serialize_to_json(result, shorten_string=True))

        return outputs
