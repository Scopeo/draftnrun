from typing import Optional
from ada_backend.schemas.components_schema import ComponentUseInfoSchema
from ada_backend.schemas.parameter_schema import PipelineParameterReadSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema


class ComponentInstanceReadSchema(ComponentInstanceSchema, ComponentUseInfoSchema):
    """Represents a component instance in the pipeline input with its definition"""

    component_name: str
    component_description: Optional[str]

    parameters: list[PipelineParameterReadSchema]
