import json
import logging
from collections.abc import Callable
from typing import Optional, Type

from pydantic import BaseModel, Field

from ada_backend.database.models import UIComponent, UIComponentProperties
from engine.components.component import Component
from engine.components.llm_call import LLMCallAgent, LLMCallInputs
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_SCORER_TOOL_DESCRIPTION = ToolDescription(
    name="Scorer",
    description="Scores content from 0 to 100 based on a criterion using AI.",
    tool_properties={
        "input": {
            "type": "string",
            "description": "The content to score",
        },
        "criteria": {
            "type": "string",
            "description": "The criterion used to evaluate and score the content from 0 to 100",
        },
    },
    required_tool_properties=["input", "criteria"],
)

PROMPT_TEMPLATE = (
    "You are an evaluation assistant. Score the following content from 0 to 100 "
    "based on the criterion provided.\n\n"
    "Content: {input}\n\n"
    "Criterion: {criteria}\n\n"
    "{additional_context_section}"
    "Provide a score from 0 to 100 where:\n"
    "- 0-20: Very poor\n"
    "- 21-40: Poor\n"
    "- 41-60: Average\n"
    "- 61-80: Good\n"
    "- 81-100: Excellent"
)

OUTPUT_FORMAT = {
    "name": "scoring_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "description": "Score from 0 to 100",
                "minimum": 0,
                "maximum": 100,
            }
        },
        "additionalProperties": False,
        "required": ["score"],
    },
}


class ScorerInputs(BaseModel):
    input: str = Field(
        description="The content to score",
        json_schema_extra={
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Input",
                placeholder="Enter the content to score",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    criteria: str = Field(
        description="The criterion used to evaluate and score the content from 0 to 100",
        json_schema_extra={
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Scoring Criteria",
                placeholder="Clarity of the message: The message must be clear and understandable",
                description="The criterion used to evaluate and score the content from 0 to 100.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    additional_context: Optional[str] = Field(
        default=None,
        description="Additional context to help with scoring",
        json_schema_extra={
            "is_tool_input": False,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Additional Context",
                placeholder="Add any additional context or instructions for scoring",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )


class ScorerOutputs(BaseModel):
    score: int = Field(description="Score from 0 to 100")


class Scorer(Component):
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return ScorerInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return ScorerOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "input", "output": "score"}

    def __init__(
        self,
        completion_service: CompletionService,
        trace_manager: TraceManager,
        tool_description: ToolDescription = DEFAULT_SCORER_TOOL_DESCRIPTION,
        component_attributes: Optional[ComponentAttributes] = None,
        capability_resolver: Optional[Callable[[list[str]], set[str]]] = None,
    ):
        if component_attributes is None:
            component_attributes = ComponentAttributes(component_instance_name=self.__class__.__name__)
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._llm_agent = LLMCallAgent(
            trace_manager=trace_manager,
            completion_service=completion_service,
            tool_description=tool_description,
            component_attributes=component_attributes,
            capability_resolver=capability_resolver,
        )

    async def _run_without_io_trace(self, inputs: ScorerInputs, ctx: Optional[dict] = None) -> ScorerOutputs:
        additional_context_section = (
            f"Additional Context: {inputs.additional_context}\n\n" if inputs.additional_context else ""
        )
        prompt = PROMPT_TEMPLATE.format(
            input=inputs.input,
            criteria=inputs.criteria,
            additional_context_section=additional_context_section,
        )

        llm_inputs = LLMCallInputs(
            messages=[ChatMessage(role="user", content=inputs.input)],
            prompt_template=prompt,
            output_format=json.dumps(OUTPUT_FORMAT),
        )

        llm_outputs = await self._llm_agent._run_without_io_trace(llm_inputs, ctx)

        result = json.loads(llm_outputs.output)
        score = int(result["score"])

        return ScorerOutputs(score=score)
