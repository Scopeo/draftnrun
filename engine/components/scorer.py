import json
import logging
from collections.abc import Callable
from typing import Optional, Type
from uuid import UUID

from pydantic import BaseModel, Field

from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
from engine.components.component import Component
from engine.components.llm_call import LLMCallAgent, LLMCallInputs
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.constants import DEFAULT_MODEL
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_SCORER_TOOL_DESCRIPTION = ToolDescription(
    name="Scorer",
    description="Scores an item from 0 to 100 based on a criterion using AI.",
    tool_properties={
        "input": {
            "type": "string",
            "description": "The item to be scored",
        },
        "criteria": {
            "type": "string",
            "description": "The criterion used to evaluate and score the item from 0 to 100",
        },
    },
    required_tool_properties=["input", "criteria"],
)

PROMPT_TEMPLATE = (
    "You are a strict, expert evaluator. Your task is to objectively assess the quality of the provided item "
    "against the given criterion and assign a precise numerical score from 0 to 100.\n\n"
    "## Item to evaluate\n"
    "{input}\n\n"
    "## Evaluation criterion\n"
    "{criteria}\n\n"
    "{additional_context_section}"
    "## Scoring guidelines\n"
    "Use the FULL range of the scale. Do NOT default to middle values — be decisive.\n"
    "- 0-10: Completely fails the criterion; fundamentally broken or irrelevant.\n"
    "- 11-25: Severe deficiencies; meets almost none of the criterion's expectations.\n"
    "- 26-40: Below average; significant gaps that undermine quality.\n"
    "- 41-55: Mediocre; partially meets the criterion but with notable weaknesses.\n"
    "- 56-70: Adequate; meets the basic expectations with minor shortcomings.\n"
    "- 71-85: Good; clearly satisfies the criterion with only small areas for improvement.\n"
    "- 86-95: Excellent; exceeds expectations with minimal or negligible issues.\n"
    "- 96-100: Exceptional; near-perfect or perfect execution of the criterion.\n\n"
    "## Instructions\n"
    "1. Analyze the item strictly through the lens of the stated criterion.\n"
    "2. Identify specific strengths and weaknesses relevant to the criterion.\n"
    "3. Assign a score that precisely reflects your assessment.\n"
    "4. Provide a concise reason justifying the score with concrete observations."
)

OUTPUT_FORMAT = {
    "score": {
        "type": "number",
        "description": "Score from 0 to 100",
    },
    "reason": {
        "type": "string",
        "description": "Brief explanation for the assigned score",
    },
}


class ScorerInputs(BaseModel):
    completion_model: str = Field(
        default=DEFAULT_MODEL,
        json_schema_extra={
            "is_tool_input": False,
            "parameter_type": ParameterType.LLM_MODEL,
            "ui_component": "Select",
            "ui_component_properties": {"label": "Model Name", "model_capabilities": ["completion"]},
        },
    )
    input: str = Field(
        description="The item to be scored",
        json_schema_extra={
            "display_order": 0,
            "parameter_type": ParameterType.STRING,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Item",
                placeholder="Enter the item to be scored",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    criteria: str = Field(
        description="The criterion used to evaluate and score the item from 0 to 100",
        json_schema_extra={
            "display_order": 1,
            "parameter_type": ParameterType.STRING,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Criteria",
                placeholder="Enter the scoring criteria, e.g., 'Clarity of the message:'",
                description="The criterion used to evaluate and score the item from 0 to 100.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    additional_context: Optional[str] = Field(
        default=None,
        description="Additional context to guide the scoring",
        json_schema_extra={
            "display_order": 2,
            "is_tool_input": False,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Additional Context",
                placeholder="[Optional] ex: 'The criteria here pertain to the clarity of the message'",
                description="Provide extra context to guide the scoring.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )


class ScorerOutputs(BaseModel):
    score: int = Field(description="Score from 0 to 100")
    reason: str = Field(description="Explanation for the assigned score")
    output: str = Field(description="Full scoring result with score and reason")


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
        return {"input": "input", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription = DEFAULT_SCORER_TOOL_DESCRIPTION,
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
        self._llm_agent = LLMCallAgent(
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
            completion_model=inputs.completion_model,
        )

        llm_outputs = await self._llm_agent._run_without_io_trace(llm_inputs, ctx)

        try:
            result = json.loads(llm_outputs.output)
        except json.JSONDecodeError as e:
            raise ValueError(f"Evaluation scoring failed: Failed to parse LLM output as JSON: {e}") from e

        score = result.get("score")
        reason = result.get("reason")

        if score is None:
            raise ValueError("Evaluation scoring failed: LLM response missing 'score' field")
        if not reason:
            raise ValueError("Evaluation scoring failed: LLM response missing 'reason' field")

        try:
            score = int(score)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Evaluation scoring failed: Invalid score value: {score}") from e

        return ScorerOutputs(score=score, reason=reason, output=json.dumps({"score": score, "reason": reason}))
