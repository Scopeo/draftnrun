"""
Router component for conditional branching.
Generates route outputs dynamically based on configured routes.
"""

import logging
from typing import Any, Dict, Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field, create_model

from ada_backend.database.models import ParameterType, UIComponent
from ada_backend.database.utils import DEFAULT_TOOL_DESCRIPTION
from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

MAX_ROUTER_ROUTES = 20

ROUTER_OPERATOR_METADATA = [
    {
        "value": "equals",
        "label": "equals",
        "description": "Check if two values are equal",
    },
]


def get_route_port_name(index: int) -> str:
    """Get the port name for a route by index (e.g., 'route_0', 'route_1')."""
    return f"route_{index}"


class RouteCondition(BaseModel):
    """Schema for a single route condition."""

    value_a: Any = Field(
        description="First value to compare",
        json_schema_extra={"parameter_type": ParameterType.JSON},
    )
    operator: str = Field(
        default="equals",
        description="Comparison operator",
        json_schema_extra={"parameter_type": ParameterType.STRING},
    )
    value_b: Any | None = Field(
        default=None,
        description="Second value to compare (defaults to value_a if not provided)",
        json_schema_extra={"parameter_type": ParameterType.JSON},
    )


class RouterInputs(BaseModel):
    """Router inputs: data to route and conditions to check."""

    input: Any = Field(
        default=None,
        description="Input data to pass through the matched route. Auto-populated from previous component if not provided.",
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
            "placeholder": "Auto-populated from previous component",
        },
    )
    routes: list[RouteCondition] = Field(
        description="List of route conditions to check",
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
            "ui_component": UIComponent.ROUTE_BUILDER,
            "ui_component_properties": {
                "label": "Routes",
                "description": "Define route conditions. Each route will have its own output.",
                "placeholder": (
                    '[{"value_a": "@{{start.additional_field}}", "operator": "equals", "value_b": "value_1"}, '
                    '{"value_a": "@{{start.additional_field}}", "operator": "equals", "value_b": "value_2"}]'
                ),
                "operators": ROUTER_OPERATOR_METADATA,
            },
        },
    )


class Router(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value
    migrated = True
    _outputs_schema_cache: Optional[Type[BaseModel]] = None

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = DEFAULT_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            tool_description=tool_description,
        )

    @classmethod
    def get_inputs_schema(cls):
        """Return the inputs schema."""
        return RouterInputs

    @classmethod
    def get_outputs_schema(cls, num_routes: Optional[int] = None) -> Type[BaseModel]:
        if cls._outputs_schema_cache is not None:
            return cls._outputs_schema_cache

        num_routes = MAX_ROUTER_ROUTES

        fields: Dict[str, tuple] = {}

        fields["matched_route"] = (
            Optional[str],
            Field(
                default=None,
                description="Name of matched route",
                json_schema_extra={
                    "parameter_type": ParameterType.STRING,
                    "disabled_as_input": True,
                },
            ),
        )
        fields["output"] = (
            Optional[Any],
            Field(
                default=None,
                description="Full input data passed through",
                json_schema_extra={
                    "parameter_type": ParameterType.JSON,
                    "disabled_as_input": True,
                },
            ),
        )

        for i in range(num_routes):
            route_name = get_route_port_name(i)
            fields[route_name] = (
                Optional[Dict[str, Any]],
                Field(
                    default=None,
                    description=f"Output for route {i}",
                    json_schema_extra={
                        "parameter_type": ParameterType.JSON,
                        "disabled_as_input": True,
                    },
                ),
            )

        cls._outputs_schema_cache = create_model("RouterOutputs", **fields)
        return cls._outputs_schema_cache

    @classmethod
    def get_canonical_input_port(cls) -> str | None:
        """Router's canonical input is 'input' - auto-populated from previous component."""
        return "input"

    @classmethod
    def get_canonical_output_port(cls) -> str | None:
        """Router's canonical output is 'output'."""
        return "output"

    def _compare_equal(self, value_a: Any, value_b: Any) -> bool:
        """Compare two values for equality."""
        return value_a == value_b

    async def _run_without_io_trace(
        self,
        inputs: RouterInputs,
        ctx: dict,
    ) -> BaseModel:

        pass_through_data = inputs.input
        routes = inputs.routes
        num_routes = len(routes)

        matched_index = None
        output_data = {
            "matched_route": None,
            "output": None,
        }

        for i, route in enumerate(routes):
            route_name = get_route_port_name(i)
            value_a = route.value_a
            value_b = route.value_b if route.value_b is not None else route.value_a

            if self._compare_equal(value_a, value_b):
                matched_index = i
                output_data[route_name] = {
                    "data": pass_through_data,
                    "should_halt": False,
                }
                if output_data["matched_route"] is None:
                    output_data["matched_route"] = route_name
                    output_data["output"] = pass_through_data
            else:
                output_data[route_name] = {
                    "data": None,
                    "should_halt": True,
                }

        if matched_index is None:
            LOGGER.warning(f"Router: No routes matched out of {num_routes} route(s)")
            output_data["output"] = (
                f"Router: No matching route found. "
                f"Evaluated {num_routes} route(s) but none matched. "
                f"Check your route conditions and input values."
            )

        OutputModel = self.get_outputs_schema()
        return OutputModel(**output_data)
