import json
import logging
from collections.abc import Callable
from typing import Optional, Type
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
from engine.components.component import Component
from engine.components.errors import CategorizationError
from engine.components.llm_call import LLMCallAgent, LLMCallInputs
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.constants import DEFAULT_MODEL
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


def _build_prompt_template(categories: dict[str, str], additional_context: Optional[str] = None) -> str:
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
        "3. A brief reason explaining why this category was selected\n\n"
        "Content to categorize:\n{{input}}"
    )

    return prompt


def _build_output_format(categories: dict[str, str]) -> str:
    category_names = list(categories.keys())

    return json.dumps({
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
    })


class CategorizerInputs(BaseModel):
    completion_model: str = Field(
        default=DEFAULT_MODEL,
        json_schema_extra={
            "is_tool_input": False,
            "parameter_type": ParameterType.LLM_MODEL,
            "ui_component": "Select",
            "ui_component_properties": {"label": "Model Name", "model_capabilities": ["completion"]},
        },
    )
    content_to_categorize: str = Field(
        default="",
        description="The content to categorize",
        json_schema_extra={
            "display_order": 0,
            "parameter_type": ParameterType.STRING,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Content to categorize",
                placeholder="Enter the content to categorize",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    categories: dict[str, str] = Field(
        description="Available categories with their descriptions to choose from.",
        json_schema_extra={
            "display_order": 1,
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
            "display_order": 2,
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
    output: str = Field(description="Full categorization result with category, score, and reason")


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
        trace_manager: TraceManager,
        tool_description: ToolDescription = DEFAULT_CATEGORIZER_TOOL_DESCRIPTION,
        component_attributes: Optional[ComponentAttributes] = None,
        temperature: float = 1.0,
        llm_api_key: Optional[str] = None,
        verbosity: Optional[str] = None,
        reasoning: Optional[str] = None,
        model_id_resolver: Optional[Callable[[str], Optional[UUID]]] = None,
        capability_resolver: Optional[Callable[[list[str]], set[str]]] = None,
    ):
        if component_attributes is None:
            component_attributes = ComponentAttributes(component_instance_name=self.__class__.__name__)
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._llm_call_agent = LLMCallAgent(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
            temperature=temperature,
            llm_api_key=llm_api_key,
            verbosity=verbosity,
            reasoning=reasoning,
            model_id_resolver=model_id_resolver,
            capability_resolver=capability_resolver,
        )

    async def _run_without_io_trace(
        self,
        inputs: CategorizerInputs,
        ctx: dict,
    ) -> CategorizerOutputs:
        prompt_template = _build_prompt_template(inputs.categories, inputs.additional_context)
        output_format = _build_output_format(inputs.categories)

        llm_inputs = LLMCallInputs(
            messages=[ChatMessage(role="user", content=inputs.content_to_categorize)],
            prompt_template=prompt_template,
            output_format=output_format,
            completion_model=inputs.completion_model,
        )

        llm_outputs = await self._llm_call_agent._run_without_io_trace(inputs=llm_inputs, ctx=ctx)
        response = llm_outputs.output

        try:
            result = json.loads(response)
        except json.JSONDecodeError as e:
            raise CategorizationError(detail=f"Failed to parse LLM output as JSON: {e}", llm_output=response)

        category = result.get("category")
        score = result.get("score")
        reason = result.get("reason")

        if not category:
            raise CategorizationError(detail="LLM response missing 'category' field", llm_output=result)
        if score is None:
            raise CategorizationError(detail="LLM response missing 'score' field", llm_output=result)
        if not reason:
            raise CategorizationError(detail="LLM response missing 'reason' field", llm_output=result)

        try:
            score = float(score)
        except (ValueError, TypeError) as e:
            raise CategorizationError(detail=f"Invalid score value: {score}", llm_output=result) from e

        return CategorizerOutputs(
            category=category,
            score=score,
            reason=reason,
            output=json.dumps({"category": category, "score": score, "reason": reason}),
        )
