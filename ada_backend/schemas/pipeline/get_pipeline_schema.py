from typing import Optional

from ada_backend.schemas.components_schema import ComponentVersionUseInfoSchema
from ada_backend.schemas.parameter_schema import PipelineParameterReadSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionReadSchema


class ComponentInstanceReadSchema(ComponentInstanceSchema, ComponentVersionUseInfoSchema):
    """Represents a component instance in the pipeline input with its definition"""

    component_name: str
    component_description: Optional[str]
    version_tag: Optional[str] = None

    parameters: list[PipelineParameterReadSchema]
    field_expressions: list[FieldExpressionReadSchema] = []
