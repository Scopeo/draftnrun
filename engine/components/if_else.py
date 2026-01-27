import logging
from enum import Enum
from typing import Any, Literal, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field, field_validator

from ada_backend.database.models import ParameterType, UIComponent
from ada_backend.database.utils import DEFAULT_TOOL_DESCRIPTION
from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


class IfElseOperator(str, Enum):
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    NUMBER_GREATER_THAN = "number_greater_than"
    NUMBER_LESS_THAN = "number_less_than"
    NUMBER_EQUAL_TO = "number_equal_to"
    NUMBER_GREATER_OR_EQUAL = "number_greater_or_equal"
    NUMBER_LESS_OR_EQUAL = "number_less_or_equal"
    BOOLEAN_IS_TRUE = "boolean_is_true"
    BOOLEAN_IS_FALSE = "boolean_is_false"
    TEXT_CONTAINS = "text_contains"
    TEXT_DOES_NOT_CONTAIN = "text_does_not_contain"
    TEXT_EQUALS = "text_equals"
    TEXT_DOES_NOT_EQUAL = "text_does_not_equal"


OPERATOR_METADATA = [
    # Unary operators
    {"value": IfElseOperator.IS_EMPTY.value, "label": "Is empty", "requires_value_b": False},
    {"value": IfElseOperator.IS_NOT_EMPTY.value, "label": "Is not empty", "requires_value_b": False},
    # Number operators
    {"value": IfElseOperator.NUMBER_GREATER_THAN.value, "label": "[Number] Is greater than", "requires_value_b": True},
    {"value": IfElseOperator.NUMBER_LESS_THAN.value, "label": "[Number] Is less than", "requires_value_b": True},
    {"value": IfElseOperator.NUMBER_EQUAL_TO.value, "label": "[Number] Is equal to", "requires_value_b": True},
    {
        "value": IfElseOperator.NUMBER_GREATER_OR_EQUAL.value,
        "label": "[Number] Is greater than or equal to",
        "requires_value_b": True,
    },
    {
        "value": IfElseOperator.NUMBER_LESS_OR_EQUAL.value,
        "label": "[Number] Is less than or equal to",
        "requires_value_b": True,
    },
    # Boolean operators
    {"value": IfElseOperator.BOOLEAN_IS_TRUE.value, "label": "[Boolean] Is true", "requires_value_b": False},
    {"value": IfElseOperator.BOOLEAN_IS_FALSE.value, "label": "[Boolean] Is false", "requires_value_b": False},
    # Text operators
    {"value": IfElseOperator.TEXT_CONTAINS.value, "label": "[Text] Contains", "requires_value_b": True},
    {
        "value": IfElseOperator.TEXT_DOES_NOT_CONTAIN.value,
        "label": "[Text] Does not contain",
        "requires_value_b": True,
    },
    {"value": IfElseOperator.TEXT_EQUALS.value, "label": "[Text] Equals", "requires_value_b": True},
    {"value": IfElseOperator.TEXT_DOES_NOT_EQUAL.value, "label": "[Text] Does not equal", "requires_value_b": True},
]


class Condition(BaseModel):
    value_a: Any = Field(description="First value to compare. Supports field expressions like @{{instance_id.output}}")
    operator: str = Field(description="Comparison operator to use")
    value_b: Any | None = Field(
        default=None,
        description="Second value to compare (not needed for unary operators). Supports field expressions.",
    )
    next_logic: Literal["AND", "OR"] | None = Field(
        default=None,
        description="How to combine this condition with the next one (AND/OR). Null for the last condition.",
    )

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        """Validate that operator is a valid IfElseOperator value."""
        valid_operators = [op.value for op in IfElseOperator]
        if v not in valid_operators:
            raise ValueError(f"Invalid operator '{v}'. Must be one of {valid_operators}")
        return v


class IfElseInputs(BaseModel):
    conditions: list[Condition] = Field(
        description=(
            "Array of conditions to evaluate with AND/OR logic. "
            "Supports field expressions like @{{instance_id.output}}."
        ),
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
            "ui_component": UIComponent.CONDITION_BUILDER,
            "ui_component_properties": {
                "label": "Conditions",
                "description": "Define conditions with AND/OR logic. Evaluate from the first condition to the last.",
                "placeholder": (
                    '[{"value_a": "@{{instance_id.output}}", "operator": "number_greater_than", "value_b": '
                    '10, "next_logic": "AND"}]'
                ),
                "available_operators": OPERATOR_METADATA,
            },
        },
    )
    output_value_if_true: Any | None = Field(
        default=None,
        description="Value to output when the whole condition evaluate to true",
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
        },
    )


class IfElseOutputs(BaseModel):
    result: bool = Field(
        description="The result of the comparison.",
        json_schema_extra={"parameter_type": ParameterType.BOOLEAN},
    )
    output: Any = Field(
        description="Pass-through data when condition is true, None otherwise.",
        json_schema_extra={"parameter_type": ParameterType.JSON},
    )
    should_halt: bool = Field(
        description="Signal to halt downstream execution (true when condition is false).",
        json_schema_extra={"parameter_type": ParameterType.BOOLEAN},
    )


class IfElse(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return IfElseInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return IfElseOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "conditions", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = DEFAULT_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )

    def _is_empty(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return len(value.strip()) == 0
        if isinstance(value, (list, dict, set, tuple)):
            return len(value) == 0
        return False

    def _to_number(self, value: Any) -> float | int:
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str) and "." in value:
            return float(value)
        return int(value)

    def _to_boolean(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "y", "on")
        return bool(value)

    def _compare_single(self, value_a: Any, value_b: Any | None, operator: IfElseOperator) -> bool:
        """Compare two values using a single operator."""
        LOGGER.debug(f"Comparing with operator: {operator.value}")

        if operator == IfElseOperator.IS_EMPTY:
            return self._is_empty(value_a)

        elif operator == IfElseOperator.IS_NOT_EMPTY:
            return not self._is_empty(value_a)

        elif operator == IfElseOperator.BOOLEAN_IS_TRUE:
            return self._to_boolean(value_a) is True

        elif operator == IfElseOperator.BOOLEAN_IS_FALSE:
            return self._to_boolean(value_a) is False

        if value_b is None:
            raise ValueError(f"Operator {operator.value} requires a second value (value_b)")

        if operator in (
            IfElseOperator.NUMBER_GREATER_THAN,
            IfElseOperator.NUMBER_LESS_THAN,
            IfElseOperator.NUMBER_EQUAL_TO,
            IfElseOperator.NUMBER_GREATER_OR_EQUAL,
            IfElseOperator.NUMBER_LESS_OR_EQUAL,
        ):
            try:
                num_a = self._to_number(value_a)
                num_b = self._to_number(value_b)
                LOGGER.debug(f"Number comparison: {num_a} {operator.value} {num_b}")

                if operator == IfElseOperator.NUMBER_GREATER_THAN:
                    return num_a > num_b
                elif operator == IfElseOperator.NUMBER_LESS_THAN:
                    return num_a < num_b
                elif operator == IfElseOperator.NUMBER_EQUAL_TO:
                    return num_a == num_b
                elif operator == IfElseOperator.NUMBER_GREATER_OR_EQUAL:
                    return num_a >= num_b
                elif operator == IfElseOperator.NUMBER_LESS_OR_EQUAL:
                    return num_a <= num_b
            except (ValueError, TypeError) as e:
                raise ValueError(f"Cannot convert values to numbers for comparison: {e}")

        str_a = str(value_a)
        str_b = str(value_b)
        LOGGER.debug(f"Text comparison: '{str_a}' {operator.value} '{str_b}'")

        if operator == IfElseOperator.TEXT_CONTAINS:
            return str_b in str_a
        elif operator == IfElseOperator.TEXT_DOES_NOT_CONTAIN:
            return str_b not in str_a
        elif operator == IfElseOperator.TEXT_EQUALS:
            return str_a == str_b
        elif operator == IfElseOperator.TEXT_DOES_NOT_EQUAL:
            return str_a != str_b

        raise ValueError(f"Unsupported operator: {operator}")

    def _evaluate_conditions(self, conditions: list[Condition], ctx: dict) -> bool:
        """Evaluate multiple conditions with AND/OR logic in sequence."""
        if not conditions:
            raise ValueError("No conditions provided for evaluation")

        LOGGER.info(f"Evaluating {len(conditions)} condition(s)")

        # Evaluate first condition
        first_cond = conditions[0]
        operator = IfElseOperator(first_cond.operator)

        result = self._compare_single(first_cond.value_a, first_cond.value_b, operator)
        LOGGER.debug(f"Condition 1: {first_cond.value_a} {operator.value} {first_cond.value_b} = {result}")

        # Evaluate remaining conditions with their logic operators
        for i in range(1, len(conditions)):
            prev_logic = conditions[i - 1].next_logic

            if prev_logic is None:
                LOGGER.warning(f"Condition {i} has no logic operator from previous condition, stopping evaluation")
                break

            current_cond = conditions[i]
            operator = IfElseOperator(current_cond.operator)

            current_result = self._compare_single(current_cond.value_a, current_cond.value_b, operator)
            LOGGER.debug(
                f"Condition {i + 1}: {current_cond.value_a} {operator.value} {current_cond.value_b} = {current_result}"
            )

            # Apply logic operator
            if prev_logic == "AND":
                result = result and current_result
                LOGGER.debug(f"Applied AND: {result}")
            elif prev_logic == "OR":
                result = result or current_result
                LOGGER.debug(f"Applied OR: {result}")

        LOGGER.info(f"Final evaluation result: {result}")
        return result

    async def _run_without_io_trace(
        self,
        inputs: IfElseInputs,
        ctx: dict,
    ) -> IfElseOutputs:
        LOGGER.info(f"Evaluating {len(inputs.conditions)} condition(s) with AND/OR logic")

        comparison_result = self._evaluate_conditions(inputs.conditions, ctx)

        if comparison_result:
            output_data = inputs.output_value_if_true
            should_halt = False
        else:
            output_data = None
            should_halt = True

        return IfElseOutputs(
            result=comparison_result,
            output=output_data,
            should_halt=should_halt,
        )
