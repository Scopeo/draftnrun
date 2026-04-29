from typing import Sequence

from ada_backend.database.models import ParameterType
from ada_backend.schemas.parameter_schema import ParameterKind, PipelineParameterReadSchema
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionReadSchema
from engine.field_expressions.parser import unparse_expression
from engine.field_expressions.serializer import from_json as expr_from_json


def filter_conflicting_parameters(
    parameters: Sequence,
    input_ports: Sequence,
) -> list:
    """
    Remove config parameters whose names collide with input ports.
    Only keep the config version if there is no enabled input with the same name,
    or if the parameter itself is already marked as kind=INPUT.
    """
    if not parameters or not input_ports:
        return list(parameters)

    input_port_names = {port.name for port in input_ports}
    return [
        param
        for param in parameters
        if not (param.name in input_port_names and getattr(param, "kind", None) != ParameterKind.INPUT)
    ]


def sort_parameters(parameters: list) -> None:
    """Sort parameters in-place: 'messages' first, then by display_order, then by name."""
    parameters.sort(
        key=lambda p: (
            0 if p.name == "messages" else 1,
            p.display_order if p.display_order is not None else float("inf"),
            p.name,
        )
    )


def build_field_expressions(input_port_instances: Sequence) -> list[FieldExpressionReadSchema]:
    result: list[FieldExpressionReadSchema] = []
    for ipi in input_port_instances:
        if ipi.field_expression:
            result.append(
                FieldExpressionReadSchema(
                    field_name=ipi.name,
                    expression_json=ipi.field_expression.expression_json,
                    expression_text=(
                        unparse_expression(expr_from_json(ipi.field_expression.expression_json))
                        if ipi.field_expression.expression_json
                        else None
                    ),
                )
            )
    return result


def synthesize_input_port_parameters(
    parameters: list,
    input_ports: Sequence,
    field_expressions: list[FieldExpressionReadSchema],
) -> list:
    """
    Filter conflicting config parameters, append input-port-based parameters,
    and sort the result (messages first, then by display_order, then name).
    """
    field_expression_by_name = {fe.field_name: fe.expression_text for fe in field_expressions}
    merged_params = filter_conflicting_parameters(parameters or [], input_ports)

    for input_port in input_ports:
        merged_params.append(
            PipelineParameterReadSchema(
                kind=ParameterKind.INPUT,
                is_tool_input=input_port.is_tool_input,
                id=input_port.id,
                name=input_port.name,
                type=input_port.parameter_type or ParameterType.STRING,
                nullable=input_port.nullable,
                default=input_port.get_default() if input_port.default is not None else None,
                ui_component=input_port.ui_component,
                ui_component_properties=input_port.ui_component_properties,
                is_advanced=input_port.is_advanced,
                drives_output_schema=input_port.drives_output_schema,
                display_order=input_port.display_order,
                value=field_expression_by_name.get(input_port.name),
            )
        )

    sort_parameters(merged_params)
    return merged_params
