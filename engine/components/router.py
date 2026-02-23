import logging
from typing import Any, Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field, PrivateAttr

from ada_backend.database.models import ParameterType, UIComponent
from ada_backend.database.utils import DEFAULT_TOOL_DESCRIPTION
from engine.components.component import Component
from engine.components.errors import NoMatchingRouteError
from engine.components.types import ComponentAttributes, ExecutionDirective, ExecutionStrategy, ToolDescription
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

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
        description="First value to compare (supports template expressions like @{{start.messages}})",
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
    """Router inputs: conditions to check and data to output to matched routes."""

    routes: list[RouteCondition] = Field(
        description="List of route conditions to check.",
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
            "ui_component": UIComponent.ROUTE_BUILDER,
            "ui_component_properties": {
                "label": "Routes",
                "description": "Define route conditions to evaluate.",
                "placeholder": (
                    '[{"value_a": "@{{start.messages}}", "operator": "equals", "value_b": "test"}, '
                    '{"value_a": "@{{start.additional_field}}", "operator": "equals", "value_b": "value_2"}]'
                ),
                "operators": ROUTER_OPERATOR_METADATA,
            },
        },
    )
    output_data: Any = Field(
        description="Data to output to matched routes (supports template expressions like @{{start.messages}}).",
        json_schema_extra={"parameter_type": ParameterType.JSON},
    )


class RouterOutputs(BaseModel):
    """Router output schema with a private directive for execution control."""

    output: Any = Field(
        description="Data passed to matched routes.",
        json_schema_extra={"parameter_type": ParameterType.JSON},
    )
    _directive: Optional[ExecutionDirective] = PrivateAttr(default=None)


class Router(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value
    migrated = True

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
        return RouterInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return RouterOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "routes", "output": "output"}

    async def _run_without_io_trace(
        self,
        inputs: RouterInputs,
        ctx: dict,
    ) -> RouterOutputs:
        """
        Router evaluates conditions and outputs user-specified data to single output port.
        Uses ExecutionDirective to control which routes execute based on edge source_port_name.
        """
        matched_routes: list[str] = []

        for i, route in enumerate(inputs.routes):
            route_name = get_route_port_name(i)
            value_b = route.value_b if route.value_b is not None else route.value_a
            matched = route.value_a == value_b
            LOGGER.info(
                f"Route {i} ({route_name}): value_a={route.value_a}, value_b={value_b}, "
                f"matched={matched}"
            )
            if matched:
                matched_routes.append(route_name)

        LOGGER.info(f"Router matched routes: {matched_routes} out of {len(inputs.routes)} total routes")
        if not matched_routes:
            LOGGER.error(f"Router: No routes matched out of {len(inputs.routes)} configured route(s)")
            raise NoMatchingRouteError(num_routes=len(inputs.routes))

        result = RouterOutputs(output=inputs.output_data)
        result._directive = ExecutionDirective(
            strategy=ExecutionStrategy.SELECTIVE_PORTS,
            selected_ports=matched_routes,
        )
        return result
