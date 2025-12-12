from typing import Sequence

from ada_backend.schemas.parameter_schema import ParameterKind


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
