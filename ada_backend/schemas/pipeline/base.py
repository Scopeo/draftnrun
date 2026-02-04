from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ada_backend.database.models import JsonSchemaType, PortSetupMode
from ada_backend.schemas.integration_schema import GraphIntegrationSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionUpdateSchema
from ada_backend.schemas.pipeline.port_instance_schema import InputPortInstanceSchema


class ToolDescriptionSchema(BaseModel):
    id: Optional[UUID] = None
    name: str
    description: str


class PortConfigurationSchema(BaseModel):
    id: Optional[UUID] = None
    component_instance_id: Optional[UUID] = None
    parameter_id: Optional[UUID] = None
    setup_mode: PortSetupMode
    field_expression_id: Optional[UUID] = None
    expression_json: Optional[dict] = None  # For creating new field expressions
    ai_name_override: Optional[str] = None
    ai_description_override: Optional[str] = None
    is_required_override: Optional[bool] = Field(
        None,
        description="Override port's required status: True=make optional port mandatory, False/None=use default",
    )
    custom_port_name: Optional[str] = None
    custom_port_description: Optional[str] = None
    custom_parameter_type: Optional[JsonSchemaType] = None
    custom_ui_component_properties: Optional[dict] = None
    json_schema_override: Optional[dict] = Field(
        None,
        description=(
            "Full JSON Schema for complex types (arrays, nested objects, etc.). Overrides simple type mapping."
        ),
    )


class ComponentInstanceSchema(BaseModel):
    """Represents a component instance in the pipeline input"""

    model_config = ConfigDict(extra="ignore")

    id: Optional[UUID] = None  # Optional - if present, update existing instance
    name: Optional[str] = None
    ref: Optional[str] = None
    is_start_node: bool = False
    component_id: UUID
    component_version_id: UUID
    parameters: list[PipelineParameterSchema]
    tool_description: Optional[ToolDescriptionSchema] = None
    integration: Optional[GraphIntegrationSchema] = None
    field_expressions: list[FieldExpressionUpdateSchema] = Field(
        default_factory=list,
        deprecated=True,
    )
    input_port_instances: list[InputPortInstanceSchema] = Field(default_factory=list)


class ComponentRelationshipSchema(BaseModel):
    """Represents a relationship between component instances"""

    parent_component_instance_id: UUID
    child_component_instance_id: UUID
    parameter_name: str  # Maps to ComponentParameterDefinition.name
    order: Optional[int] = None
