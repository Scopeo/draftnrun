import logging
from typing import Any, Dict, Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, ConfigDict, Field, create_model

from ada_backend.database.models import ParameterType, UIComponent
from ada_backend.database.utils import DEFAULT_TOOL_DESCRIPTION
from engine.components.component import Component
from engine.components.errors import NoMatchingRouteError
from engine.components.types import ComponentAttributes, ExecutionDirective, ExecutionStrategy, ToolDescription
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

MAX_ROUTER_ROUTES = 10

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
        description=(
            "Input data to pass through the matched route. Auto-populated from previous component if not provided."
        ),
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

        for i in range(num_routes):
            route_name = get_route_port_name(i)
            fields[route_name] = (
                Any,
                Field(
                    default=None,
                    description=f"Output for route {i}",
                    json_schema_extra={
                        "parameter_type": ParameterType.JSON,
                        "disabled_as_input": True,
                    },
                ),
            )

        schema = create_model("RouterOutputs", __config__=ConfigDict(extra="allow"), **fields)
        cls._outputs_schema_cache = schema

        return schema

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "input", "output": None}

    def _compare_equal(self, value_a: Any, value_b: Any) -> bool:
        """Compare two values for equality."""
        return value_a == value_b

    async def _run_without_io_trace(
        self,
        inputs: RouterInputs,
        ctx: dict,
    ) -> BaseModel:
        OutputModel = self.get_outputs_schema()

        output_data: dict = {}

        for i, route in enumerate(inputs.routes):
            route_name = get_route_port_name(i)
            value_b = route.value_b if route.value_b is not None else route.value_a
            if self._compare_equal(route.value_a, value_b):
                LOGGER.info(f"Route {i} matched")

                output_data[route_name] = inputs.input

        if not output_data:
            LOGGER.error(f"Router: No routes matched out of {len(inputs.routes)} configured route(s)")
            raise NoMatchingRouteError(num_routes=len(inputs.routes))

        return OutputModel(
            **output_data,
            _directive=ExecutionDirective(
                strategy=ExecutionStrategy.SELECTIVE_PORTS,
                selected_ports=list(output_data.keys()),
            ),
        )
