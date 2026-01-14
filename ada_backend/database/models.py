import json
import logging
import uuid
from enum import StrEnum
from typing import List, Optional, Type, Union

import sqlalchemy as sa
from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, mapped_column, relationship

from ada_backend.database.utils import camel_to_snake
from ada_backend.schemas.llm_models_schema import ModelCapabilityEnum
from settings import settings

Base = declarative_base()
LOGGER = logging.getLogger(__name__)


class ModelCapabilityList(TypeDecorator):
    """Custom type that converts between list[ModelCapabilityEnum] and JSONB"""

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert enum list to JSON array of strings for storage"""
        if value is None:
            return None
        if isinstance(value, list):
            return [cap.value if isinstance(cap, ModelCapabilityEnum) else str(cap) for cap in value]
        return value

    def process_result_value(self, value, dialect):
        """Convert JSON array of strings to enum list when reading"""
        if value is None:
            return None
        if isinstance(value, list):
            return [ModelCapabilityEnum(cap) if isinstance(cap, str) else cap for cap in value]
        return value


if not settings.FERNET_KEY:
    raise ValueError(
        "FERNET_KEY is not set in the environment. It is required for secure storage.",
    )
CIPHER = Fernet(settings.FERNET_KEY)


def make_pg_enum(enum_cls: Type[StrEnum], schema: str = None) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum_cls,
        name=camel_to_snake(enum_cls.__name__),
        values_callable=lambda x: [e.value for e in x],
        native_enum=True,
        schema=schema,
    )


# --- Enums ---
class ParameterType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    COMPONENT = "component"
    TOOL = "tool"
    DATA_SOURCE = "data_source"
    SECRETS = "secrets"
    LLM_API_KEY = "llm_api_key"
    LLM_MODEL = "llm_model"


class OrgSecretType(StrEnum):
    LLM_API_KEY = "llm_api_key"
    PASSWORD = "password"


class ApiKeyType(StrEnum):
    PROJECT = "project"
    ORGANIZATION = "organization"


class ProjectType(StrEnum):
    AGENT = "agent"
    WORKFLOW = "workflow"


class NodeType(StrEnum):
    """Enumeration of node types."""

    GRAPH = "graph_runner"
    COMPONENT = "component_instance"


class EnvType(StrEnum):
    DRAFT = "draft"
    PRODUCTION = "production"


class CallType(StrEnum):
    API = "api"
    SANDBOX = "sandbox"
    QA = "qa"


class ResponseFormat(StrEnum):
    BASE64 = "base64"
    URL = "url"
    S3_KEY = "s3_key"


class UIComponent(StrEnum):
    AUTOCOMPLETE = "Autocomplete"
    CHECKBOX = "Checkbox"
    COMBOBOX = "Combobox"
    DATE_TIME_PICKER = "Date Time Picker"
    EDITORS = "Editors"
    FILE_INPUT = "File Input"
    RADIO = "Radio"
    CUSTOM_INPUT = "Custom Input"
    RANGE_SLIDER = "Range Slider"
    RATING = "Rating"
    SELECT = "Select"
    SLIDER = "Slider"
    SWITCH = "Switch"
    TEXTAREA = "Textarea"
    TEXTFIELD = "Textfield"
    FILE_UPLOAD = "FileUpload"
    JSON_BUILDER = "JSON Builder"


class SourceType(StrEnum):
    """Enumeration of source types."""

    GOOGLE_DRIVE = "google_drive"
    LOCAL = "local"
    DATABASE = "database"
    WEBSITE = "website"


class TaskStatus(StrEnum):
    """Enumeration of task statuses."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ReleaseStage(StrEnum):
    """Enumeration of feature flags."""

    BETA = "beta"
    EARLY_ACCESS = "early_access"
    PUBLIC = "public"
    INTERNAL = "internal"


class CronEntrypoint(StrEnum):
    AGENT_INFERENCE = "agent_inference"
    DUMMY_PRINT = "dummy_print"
    ENDPOINT_POLLING = "endpoint_polling"


class CronStatus(StrEnum):
    COMPLETED = "completed"
    ERROR = "error"
    RUNNING = "running"


class EvaluationType(StrEnum):
    BOOLEAN = "boolean"
    SCORE = "score"
    FREE_TEXT = "free_text"


class PortType(StrEnum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


class EntityType(StrEnum):
    LLM = "llm"
    COMPONENT = "component"
    PARAMETER_VALUE = "parameter_value"


class SelectOption(BaseModel):
    """Option for Select and similar UI components"""

    value: str
    label: str


class UIComponentProperties(BaseModel):
    """Properties for different UI components"""

    model_config = ConfigDict(
        extra="allow",  # Allows additional properties not explicitly defined
        exclude_unset=True,  # Excludes fields that weren't explicitly set
        exclude_none=True,  # Excludes fields with None values
    )

    # Common properties
    label: Optional[str] = None
    placeholder: Optional[str] = None
    description: Optional[str] = None

    # Select/Combobox properties
    options: Optional[List[SelectOption]] = None

    # Slider/Range properties
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[Union[int, float]] = None
    marks: Optional[bool] = None

    # Password field property
    type: Optional[str] = Field(None, description="Set to 'password' for password fields")

    # File upload property
    accept: Optional[str] = None
    multiple: Optional[bool] = None


def cast_value(
    parameter_type: ParameterType,
    unresolved_value: str,
) -> str | int | float | bool | dict:
    if unresolved_value is None or unresolved_value == "None" or unresolved_value == "null":
        return None
    if parameter_type == ParameterType.STRING:
        return unresolved_value
    elif parameter_type == ParameterType.INTEGER:
        return int(unresolved_value)
    elif parameter_type == ParameterType.FLOAT:
        return float(unresolved_value)
    elif parameter_type == ParameterType.BOOLEAN:
        return unresolved_value.lower() in ("true", "1")
    elif parameter_type == ParameterType.JSON or parameter_type == ParameterType.DATA_SOURCE:
        return json.loads(unresolved_value)
    elif parameter_type == ParameterType.LLM_API_KEY:
        return unresolved_value
    elif parameter_type == ParameterType.COMPONENT or parameter_type == ParameterType.TOOL:
        raise ValueError("Parameter type COMPONENT or TOOL is not supported for BasicParameters")
    elif parameter_type == ParameterType.LLM_MODEL:
        return unresolved_value
    else:
        raise ValueError(f"Unsupported value type: {parameter_type}")


# --- Models ---
class Component(Base):
    """
    Defines reusable components, which can be agents or other classes/functions
    that are instantiated dynamically.
    """

    __tablename__ = "components"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = mapped_column(String, unique=True, nullable=False)
    base_component = mapped_column(String, nullable=True)
    icon = mapped_column(String, nullable=True)
    description = mapped_column(Text, nullable=True)
    is_agent = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    function_callable = mapped_column(Boolean, nullable=False, default=False)
    can_use_function_calling = mapped_column(Boolean, nullable=False, default=False)
    is_protected = mapped_column(Boolean, nullable=False, default=False)

    categories = relationship(
        "ComponentCategory",
        back_populates="component",
        cascade="all, delete-orphan",
    )

    versions = relationship(
        "ComponentVersion",
        back_populates="component",
        cascade="all, delete-orphan",
        order_by="ComponentVersion.created_at.desc()",
    )

    def __str__(self):
        return f"Component({self.name})"


class ComponentVersion(Base):
    """
    Defines versions for components to track changes and updates over time.
    """

    __tablename__ = "component_versions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_tag = mapped_column(String, nullable=False)
    changelog = mapped_column(Text, nullable=True)

    description = mapped_column(Text, nullable=True)
    integration_id = mapped_column(UUID(as_uuid=True), ForeignKey("integrations.id"), nullable=True)
    default_tool_description_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_descriptions.id"),
        nullable=True,
    )
    release_stage = mapped_column(make_pg_enum(ReleaseStage), nullable=False, default=ReleaseStage.BETA)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    component = relationship("Component")
    component_cost = relationship(
        "ComponentCost", back_populates="component_version", uselist=False, cascade="all, delete-orphan"
    )
    definitions = relationship(
        "ComponentParameterDefinition",
        back_populates="component_version",
        cascade="all, delete-orphan",
    )
    port_definitions = relationship(
        "PortDefinition",
        back_populates="component_version",
        cascade="all, delete-orphan",
    )
    child_definitions = relationship(
        "ComponentParameterChildRelationship",
        back_populates="child_component",
        cascade="all, delete-orphan",
    )
    parameter_groups = relationship(
        "ComponentParameterGroup",
        back_populates="component_version",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("version_tag ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="check_version_semver"),
        UniqueConstraint("component_id", "version_tag", name="uq_component_version"),
        UniqueConstraint("component_id", "id", name="uq_component_versions_component_id_id"),
    )

    def __str__(self):
        return f"ComponentVersion(component_id={self.component_id}, version_tag={self.version_tag})"


class ReleaseStageToCurrentVersionMapping(Base):
    """
    Maps release stages to the 'current' version of a component.

    Invariant DB garanti:
      - (component_id, release_stage) est unique.
      - component_version_id pointe sur une version qui appartient au même component_id.
    """

    __tablename__ = "release_stage_to_current_version_mappings"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)

    component_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="CASCADE"), nullable=False, index=True
    )
    release_stage = mapped_column(
        make_pg_enum(ReleaseStage),
        nullable=False,
    )
    component_version_id = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    component_version = relationship("ComponentVersion")

    __table_args__ = (
        ForeignKeyConstraint(
            ["component_id", "component_version_id"],
            ["component_versions.component_id", "component_versions.id"],
            ondelete="CASCADE",
            name="fk_mapping_same_component",
        ),
        UniqueConstraint("component_id", "release_stage", name="uq_component_release_stage"),
        Index(
            "idx_current_by_component_stage",
            "component_id",
            "release_stage",
            unique=True,
        ),
    )

    def __str__(self) -> str:
        return (
            f"ReleaseStageToCurrentVersionMapping(component_id={self.component_id}, "
            f"release_stage={self.release_stage}, component_version_id={self.component_version_id})"
        )


class Integration(Base):
    __tablename__ = "integrations"

    id = mapped_column(UUID(as_uuid=True), primary_key=True)
    name = mapped_column(String, nullable=False)
    service = mapped_column(String, nullable=False)


class SecretIntegration(Base):
    __tablename__ = "secret_integrations"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    integration_id = mapped_column(UUID(as_uuid=True), ForeignKey("integrations.id"))
    encrypted_access_token = mapped_column(String)
    encrypted_refresh_token = mapped_column(String)
    expires_in = mapped_column(Integer)
    token_last_updated = mapped_column(DateTime(timezone=True))

    secret_integration_component_instances = relationship(
        "IntegrationComponentInstanceRelationship",
        back_populates="secret_integration",
    )

    def set_access_token(self, access_token: str) -> None:
        """Encrypts and sets the access token."""
        self.encrypted_access_token = CIPHER.encrypt(access_token.encode()).decode()

    def set_refresh_token(self, refresh_token: str) -> None:
        """Encrypts and sets the refresh token."""
        self.encrypted_refresh_token = CIPHER.encrypt(refresh_token.encode()).decode()

    def get_access_token(self) -> str:
        return CIPHER.decrypt(self.encrypted_access_token.encode()).decode()

    def get_refresh_token(self) -> str:
        return CIPHER.decrypt(self.encrypted_refresh_token.encode()).decode()


class IntegrationComponentInstanceRelationship(Base):
    __tablename__ = "integration_component_instance_relationships"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    secret_integration_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("secret_integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_instance_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    secret_integration = relationship("SecretIntegration")
    component_instance = relationship("ComponentInstance")


class Category(Base):
    """
    Defines categories for components, allowing for better organization and retrieval.
    """

    __tablename__ = "categories"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = mapped_column(String, unique=True, nullable=False)
    description = mapped_column(Text, nullable=True)
    icon = mapped_column(String, nullable=True)
    display_order = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    components = relationship(
        "ComponentCategory",
        back_populates="category",
        cascade="all, delete-orphan",
    )

    def __str__(self):
        return f"Category({self.name})"


class ComponentCategory(Base):
    """
    Defines the relationship between components and categories.
    A component can belong to multiple categories.
    """

    __tablename__ = "component_categories"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )

    component = relationship("Component", back_populates="categories")
    category = relationship("Category", back_populates="components")


class GraphRunner(Base):
    """
    Defines graph runners, which are used to execute a graph of components.
    """

    __tablename__ = "graph_runners"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    tag_version = mapped_column(String, nullable=True)
    version_name = mapped_column(String, nullable=True)
    change_log = mapped_column(Text, nullable=True)

    graph_edges = relationship("GraphRunnerEdge", back_populates="graph_runner")
    nodes = relationship("GraphRunnerNode", back_populates="graph_runner")
    port_mappings = relationship("PortMapping", back_populates="graph_runner")
    modification_history = relationship(
        "GraphRunnerModificationHistory",
        back_populates="graph_runner",
        cascade="all, delete-orphan",
        order_by="GraphRunnerModificationHistory.created_at.desc()",
    )

    __table_args__ = (
        CheckConstraint(
            "tag_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="check_tag_version_semver",
        ),
    )

    def __str__(self):
        return f"Graph Runner({self.id})"


class GraphRunnerModificationHistory(Base):
    """Tracks modification history for graph runners by storing hash of graph structure."""

    __tablename__ = "graph_runner_modification_history"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    graph_runner_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = mapped_column(UUID(as_uuid=True), nullable=True)
    modification_hash = mapped_column(String, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    graph_runner = relationship("GraphRunner", back_populates="modification_history")

    def __str__(self):
        return f"GraphRunnerModificationHistory(graph_runner_id={self.graph_runner_id}, created_at={self.created_at})"


class ComponentParameterDefinition(Base):
    """
    Defines the parameters that a component can accept, including subinputs.
    """

    __tablename__ = "component_parameter_definitions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_version_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = mapped_column(String, nullable=False)
    type = mapped_column(make_pg_enum(ParameterType), nullable=False)
    nullable = mapped_column(Boolean, nullable=False, default=False)
    order = mapped_column(Integer, nullable=True)
    default = mapped_column(String, nullable=True)
    ui_component = mapped_column(make_pg_enum(UIComponent), nullable=True)
    ui_component_properties = mapped_column(JSON, nullable=True)
    is_advanced = mapped_column(Boolean, nullable=False, default=False)
    model_capabilities = mapped_column(JSONB, nullable=True)

    component_version = relationship("ComponentVersion", back_populates="definitions")
    parameter_group_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parameter_groups.id", name="fk_component_parameter_definitions_parameter_group_id"),
        nullable=True,
    )
    parameter_order_within_group = mapped_column(Integer, nullable=True)

    parameter_group = relationship("ParameterGroup")
    child_components = relationship(
        "ComponentParameterChildRelationship", back_populates="component_parameter_definition"
    )

    def get_default(self):
        return cast_value(self.type, self.default)

    def __str__(self):
        return f"CompParamDef(name={self.name}, type={self.type}, is_advanced={self.is_advanced})"


class ComponentParameterChildRelationship(Base):
    """
    Defines the relationship between a component parameter (type component) and a child component.
    """

    __tablename__ = "comp_param_child_comps_relationships"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_parameter_definition_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_parameter_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    child_component_version_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    component_parameter_definition = relationship("ComponentParameterDefinition", back_populates="child_components")
    child_component = relationship("ComponentVersion", back_populates="child_definitions")

    def __str__(self):
        return (
            f"CompParamToChildCompRel(component_parameter_definition_id={self.component_parameter_definition_id}, "
            f"child_component_version_id={self.child_component_version_id})"
        )


class ComponentInstance(Base):
    """Configured instances of components."""

    __tablename__ = "component_instances"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_version_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = mapped_column(String, nullable=True, index=True)
    ref = mapped_column(String, nullable=True, index=True)
    tool_description_id = mapped_column(UUID(as_uuid=True), ForeignKey("tool_descriptions.id"), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    component_version = relationship("ComponentVersion")
    tool_description = relationship("ToolDescription")
    basic_parameters = relationship(
        "BasicParameter",
        back_populates="component_instance",
        cascade="all, delete-orphan",
    )
    sub_inputs = relationship(
        "ComponentSubInput",
        foreign_keys="ComponentSubInput.parent_component_instance_id",
        back_populates="parent_component_instance",
        cascade="all, delete-orphan",
    )
    used_by = relationship(
        "ComponentSubInput",
        foreign_keys="ComponentSubInput.child_component_instance_id",
        back_populates="child_component_instance",
        cascade="all, delete-orphan",
    )
    source_port_mappings = relationship(
        "PortMapping",
        foreign_keys="PortMapping.source_instance_id",
        back_populates="source_instance",
        cascade="all, delete-orphan",
    )
    target_port_mappings = relationship(
        "PortMapping",
        foreign_keys="PortMapping.target_instance_id",
        back_populates="target_instance",
        cascade="all, delete-orphan",
    )
    relationships = relationship(
        "IntegrationComponentInstanceRelationship",
        back_populates="component_instance",
        cascade="all, delete-orphan",
    )

    def __str__(self):
        return f"ComponentInstance(ref={self.ref})"


class ParameterGroup(Base):
    """Global parameter group definitions that can be reused across components."""

    __tablename__ = "parameter_groups"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(String, nullable=False)

    parameters = relationship("ComponentParameterDefinition", back_populates="parameter_group")


class ComponentParameterGroup(Base):
    """Component version-specific configuration for parameter groups.
    Help define for a given component version the order of the groups.
    """

    __tablename__ = "component_parameter_groups"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component_version_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("component_versions.id", ondelete="CASCADE"), nullable=False
    )
    parameter_group_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parameter_groups.id", ondelete="CASCADE", name="fk_component_parameter_groups_parameter_group_id"),
        nullable=False,
    )
    group_order_within_component = mapped_column(Integer, nullable=False, default=0)

    component_version = relationship("ComponentVersion", back_populates="parameter_groups")
    parameter_group = relationship("ParameterGroup")

    __table_args__ = (
        sa.UniqueConstraint("component_version_id", "parameter_group_id", name="uq_component_version_parameter_group"),
    )


class GraphRunnerNode(Base):
    """Represents a node in a graph runner, which can be a component instance or a graph runner itself."""

    __tablename__ = "graph_runner_nodes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    node_id = mapped_column(UUID(as_uuid=True), unique=True, index=True, nullable=False)
    graph_runner_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runners.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_type = mapped_column(make_pg_enum(NodeType), nullable=False)
    is_start_node = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    graph_runner = relationship("GraphRunner", back_populates="nodes")
    outgoing_edges = relationship(
        "GraphRunnerEdge",
        foreign_keys="GraphRunnerEdge.source_node_id",
        back_populates="input_nodes",
        cascade="all, delete-orphan",
    )
    incoming_edges = relationship(
        "GraphRunnerEdge",
        foreign_keys="GraphRunnerEdge.target_node_id",
        back_populates="target_nodes",
        cascade="all, delete-orphan",
    )

    def __str__(self):
        return (
            f"GraphRunnerNode(node_id={self.node_id}, graph_runner_id={self.graph_runner_id}, "
            f"node_type={self.node_type}, is_start_node={self.is_start_node})"
        )


class BasicParameter(Base):
    """
    Represents parameters for a component instance, supporting static values
    or referencing secrets for secure storage.
    """

    __tablename__ = "basic_parameters"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_instance_id = mapped_column(UUID(as_uuid=True), ForeignKey("component_instances.id"), nullable=False)
    parameter_definition_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_parameter_definitions.id"),
        nullable=False,
    )
    value = mapped_column(String, nullable=True)
    organization_secret_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_secrets.id", ondelete="CASCADE"), nullable=True
    )
    order = mapped_column(Integer, nullable=True)

    component_instance = relationship("ComponentInstance", back_populates="basic_parameters")
    parameter_definition = relationship("ComponentParameterDefinition")
    organization_secret = relationship("OrganizationSecret", back_populates="basic_parameters")

    # Ensure that either a value or a organization secret is provided, but not both
    __table_args__ = (
        CheckConstraint(
            sqltext=(
                "(value IS NOT NULL AND organization_secret_id IS NULL) OR "
                "(value IS NULL AND organization_secret_id IS NOT NULL)"
            ),
            name="check_value_or_organization_secret",
        ),
    )

    def get_value(self):
        """Fetches the actual value of the parameter, resolving secrets if necessary."""
        unresolved_value = self.value
        if self.organization_secret:
            unresolved_value = self.organization_secret.get_secret()
        return cast_value(self.parameter_definition.type, unresolved_value)

    def __str__(self):
        value_display = (
            f"organization_secret_id={self.organization_secret_id}"
            if self.organization_secret_id
            else f"value={self.value}"
        )
        return f"BasicParameter({value_display})"


class ComponentGlobalParameter(Base):
    """
    Parameters enforced globally for a component (shared across all instances).

    Note: No organization-level scoping; values are the same across organizations.
    Lists are represented with multiple rows of the same
    (component_id, parameter_definition_id) with different order values.
    """

    __tablename__ = "component_global_parameters"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_version_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    parameter_definition_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_parameter_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value = mapped_column(String, nullable=True)
    order = mapped_column(Integer, nullable=True)

    component_version = relationship("ComponentVersion")
    parameter_definition = relationship("ComponentParameterDefinition")
    __table_args__ = (
        # Enforce uniqueness for scalar values (order IS NULL)
        sa.Index(
            "uq_comp_global_param_scalar",
            "component_version_id",
            "parameter_definition_id",
            unique=True,
            postgresql_where=sa.text('"order" IS NULL'),
        ),
        # Enforce uniqueness for list values (order IS NOT NULL)
        sa.Index(
            "uq_comp_global_param_list",
            "component_version_id",
            "parameter_definition_id",
            "order",
            unique=True,
            postgresql_where=sa.text('"order" IS NOT NULL'),
        ),
    )

    def get_value(self):
        """Cast string value to the typed value from its definition."""
        return cast_value(self.parameter_definition.type, self.value)


class ComponentSubInput(Base):
    """Specifies other component instances required as inputs for a component."""

    __tablename__ = "component_sub_inputs"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    parent_component_instance_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    child_component_instance_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    parameter_definition_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_parameter_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    order = mapped_column(Integer, nullable=True)

    parent_component_instance = relationship(
        "ComponentInstance",
        foreign_keys=[parent_component_instance_id],
        back_populates="sub_inputs",
    )
    child_component_instance = relationship(
        "ComponentInstance",
        foreign_keys=[child_component_instance_id],
        back_populates="used_by",
    )
    parameter_definition = relationship("ComponentParameterDefinition")


class GraphRunnerEdge(Base):
    """Represents an edge between two nodes of a graph runner."""

    __tablename__ = "graph_runner_edges"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    source_node_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runner_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runner_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    graph_runner_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runners.id", ondelete="CASCADE"),
        nullable=False,
    )
    order = mapped_column(Integer, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    graph_runner = relationship("GraphRunner", foreign_keys=[graph_runner_id], back_populates="graph_edges")
    input_nodes = relationship(
        "GraphRunnerNode",
        foreign_keys=[source_node_id],
        back_populates="outgoing_edges",
    )
    target_nodes = relationship(
        "GraphRunnerNode",
        foreign_keys=[target_node_id],
        back_populates="incoming_edges",
    )

    def __str__(self):
        return (
            f"GraphRunnerEdge(input={self.source_node_id}, output={self.target_node_id}, "
            f"order={self.order}, graph={self.graph_runner_id})"
        )


class PortDefinition(Base):
    """Stores the I/O schema for each component type."""

    __tablename__ = "port_definitions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component_version_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = mapped_column(String, nullable=False)
    port_type = mapped_column(make_pg_enum(PortType), nullable=False)
    is_canonical = mapped_column(Boolean, nullable=False, default=False)
    description = mapped_column(Text, nullable=True)
    ui_component = mapped_column(make_pg_enum(UIComponent), nullable=True)
    ui_component_properties = mapped_column(JSONB, nullable=True)
    component_version = relationship("ComponentVersion", back_populates="port_definitions")

    __table_args__ = (
        sa.UniqueConstraint("component_version_id", "name", "port_type", name="unique_component_version_port"),
    )


class PortMapping(Base):
    """Stores the specific wiring for a GraphRunner instance."""

    __tablename__ = "port_mappings"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    graph_runner_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runners.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_instance_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_port_definition_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("port_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_instance_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_port_definition_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("port_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    dispatch_strategy = mapped_column(String, nullable=False, default="direct")

    graph_runner = relationship("GraphRunner", back_populates="port_mappings")
    source_instance = relationship(
        "ComponentInstance",
        foreign_keys=[source_instance_id],
        back_populates="source_port_mappings",
    )
    target_instance = relationship(
        "ComponentInstance",
        foreign_keys=[target_instance_id],
        back_populates="target_port_mappings",
    )
    source_port_definition = relationship(
        "PortDefinition",
        foreign_keys=[source_port_definition_id],
    )
    target_port_definition = relationship(
        "PortDefinition",
        foreign_keys=[target_port_definition_id],
    )


class ToolDescription(Base):
    """Defines metadata for tools used in OpenAI function calling."""

    __tablename__ = "tool_descriptions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = mapped_column(String, nullable=False)
    description = mapped_column(Text, nullable=False)
    tool_properties = mapped_column(JSON, nullable=True, default=dict)
    required_tool_properties = mapped_column(JSON, nullable=True, default=list)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __str__(self):
        return f"ToolDescription({self.name})"


class FieldExpression(Base):
    """Stores field expressions for component instances.

    One row per (component_instance, field_name).
    """

    __tablename__ = "field_expressions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_instance_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("component_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name = mapped_column(String, nullable=False)
    expression_json = mapped_column(JSONB, nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "component_instance_id",
            "field_name",
            name="uq_field_expression_instance_field",
        ),
    )


class Project(Base):
    """
    Tracks projects, which are collections of components and their configurations.
    """

    __tablename__ = "projects"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = mapped_column(String, unique=False, nullable=False)
    type = mapped_column(make_pg_enum(ProjectType), nullable=False, default=ProjectType.WORKFLOW)
    description = mapped_column(Text, nullable=True)
    organization_id = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    api_keys = relationship(
        "ProjectApiKey",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    envs = relationship("ProjectEnvironmentBinding", back_populates="project")

    # Quality Assurance relationships
    datasets = relationship("DatasetProject", back_populates="project", cascade="all, delete-orphan")

    usage = relationship("Usage", back_populates="project", cascade="all, delete-orphan")

    __mapper_args__ = {"polymorphic_on": type, "polymorphic_identity": "base"}

    def __str__(self):
        return f"Project({self.name})"


class WorkflowProject(Project):
    __tablename__ = "workflow_projects"
    id = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), primary_key=True)

    __mapper_args__ = {"polymorphic_identity": ProjectType.WORKFLOW.value}


class AgentProject(Project):
    __tablename__ = "agent_projects"
    id = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), primary_key=True)

    __mapper_args__ = {"polymorphic_identity": ProjectType.AGENT.value}


class ProjectEnvironmentBinding(Base):
    """Binds a project environment to a specific graph version."""

    __tablename__ = "project_env_binding"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    project_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    environment = mapped_column(make_pg_enum(EnvType), nullable=True)
    graph_runner_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runners.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="envs")
    graph_runner = relationship("GraphRunner")

    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "environment",
            name="uq_project_environment",
        ),
    )


class OrganizationSecret(Base):
    """
    Stores secrets (key-value pairs) for organization ensuring secure storage via encryption.
    """

    __tablename__ = "organization_secrets"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    organization_id = mapped_column(UUID(as_uuid=True), nullable=False)
    key = mapped_column(String, nullable=False, index=True)
    secret_type = mapped_column(make_pg_enum(OrgSecretType), nullable=False, default=OrgSecretType.LLM_API_KEY)
    encrypted_secret = mapped_column(String, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    basic_parameters = relationship(
        "BasicParameter",
        back_populates="organization_secret",
        cascade="all, delete-orphan",
    )
    source_attributes = relationship(
        "SourceAttributes",
        back_populates="source_db_url_secret",
        passive_deletes=True,
    )

    def __str__(self):
        return f"OrganizationSecret(organization_id={self.organization_id}, key={self.key})"

    def set_secret(self, secret: str) -> None:
        """Encrypts the provided secret and stores it."""
        self.encrypted_secret = CIPHER.encrypt(secret.encode()).decode()

    def get_secret(self) -> str:
        """Decrypts and returns the stored secret."""
        return CIPHER.decrypt(self.encrypted_secret.encode()).decode()


class GlobalSecret(Base):
    """
    Stores global secrets (key-value pairs) for the application, ensuring
    secure storage via encryption. These act as DB-backed settings-level
    credentials (e.g. OPENAI_API_KEY) available to all organizations
    unless overridden at the organization level.
    """

    __tablename__ = "global_secrets"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    key = mapped_column(String, nullable=False, unique=True, index=True)
    encrypted_secret = mapped_column(String, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __str__(self):
        return f"GlobalSecret(key={self.key})"

    def set_secret(self, secret: str) -> None:
        """Encrypts the provided secret and stores it."""
        self.encrypted_secret = CIPHER.encrypt(secret.encode()).decode()

    def get_secret(self) -> str:
        """Decrypts and returns the stored secret."""
        return CIPHER.decrypt(self.encrypted_secret.encode()).decode()


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    type = mapped_column(make_pg_enum(ApiKeyType), nullable=False)
    public_key = mapped_column(String, unique=True, nullable=False)
    name = mapped_column(String, nullable=False)
    is_active = mapped_column(Boolean, nullable=False, default=True)
    creator_user_id = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    revoker_user_id = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"polymorphic_on": type, "polymorphic_identity": "base"}


class ProjectApiKey(ApiKey):
    __tablename__ = "project_api_keys"
    id = mapped_column(UUID(as_uuid=True), ForeignKey("api_keys.id"), primary_key=True)
    project_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    project = relationship("Project", back_populates="api_keys")

    __mapper_args__ = {"polymorphic_identity": ApiKeyType.PROJECT.value}


class OrgApiKey(ApiKey):
    __tablename__ = "org_api_keys"
    id = mapped_column(UUID(as_uuid=True), ForeignKey("api_keys.id"), primary_key=True)
    organization_id = mapped_column(UUID(as_uuid=True), index=True, nullable=False)

    __mapper_args__ = {"polymorphic_identity": ApiKeyType.ORGANIZATION.value}


class IngestionTask(Base):
    """
    Represents a task for data ingestion.
    """

    __tablename__ = "ingestion_tasks"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    source_id = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=True)
    # TODO duplicated org_id with data_sources
    organization_id = mapped_column(UUID(as_uuid=True), nullable=False)
    source_name = mapped_column(String, nullable=False)
    source_type = mapped_column(make_pg_enum(SourceType), nullable=False)
    status = mapped_column(make_pg_enum(TaskStatus), nullable=False)
    result_metadata = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    source = relationship("DataSource", back_populates="ingestion_tasks")

    def __str__(self):
        return f"Task({self.source_name}) - {self.status})"


class DataSource(Base):
    """
    Represents a data source with database and vector store configurations.
    """

    __tablename__ = "data_sources"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = mapped_column(String, nullable=False)
    type = mapped_column(make_pg_enum(SourceType), nullable=False)
    organization_id = mapped_column(UUID(as_uuid=True), nullable=False)
    database_schema = mapped_column(String, nullable=True)
    database_table_name = mapped_column(String, nullable=True)
    qdrant_collection_name = mapped_column(String, nullable=True)
    qdrant_schema = mapped_column(JSON, nullable=True)
    embedding_model_reference = mapped_column(String, nullable=False, default="openai:text-embedding-3-large")
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_ingestion_time = mapped_column(DateTime(timezone=True), nullable=True)

    ingestion_tasks = relationship("IngestionTask", back_populates="source")
    attributes = relationship(
        "SourceAttributes",
        back_populates="source",
        cascade="all, delete-orphan",
    )

    def __str__(self):
        return f"DataSource({self.name})"


class SourceAttributes(Base):
    """
    Represents attributes for a data source.
    """

    __tablename__ = "source_attributes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    source_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_token = mapped_column(String, nullable=True)
    path = mapped_column(String, nullable=True)
    list_of_files_from_local_folder = mapped_column(JSON, nullable=True)
    folder_id = mapped_column(String, nullable=True)
    source_db_url = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_secrets.id", ondelete="SET NULL"), nullable=True
    )
    source_table_name = mapped_column(String, nullable=True)
    id_column_name = mapped_column(String, nullable=True)
    text_column_names = mapped_column(JSON, nullable=True)
    source_schema_name = mapped_column(String, nullable=True)
    chunk_size = mapped_column(Integer, nullable=True)
    chunk_overlap = mapped_column(Integer, nullable=True)
    metadata_column_names = mapped_column(JSON, nullable=True)
    timestamp_column_name = mapped_column(String, nullable=True)
    url_pattern = mapped_column(String, nullable=True)
    update_existing = mapped_column(Boolean, nullable=False, default=False)
    query_filter = mapped_column(String, nullable=True)
    timestamp_filter = mapped_column(String, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    source = relationship("DataSource", back_populates="attributes")
    source_db_url_secret = relationship("OrganizationSecret", back_populates="source_attributes")

    def __str__(self):
        return f"SourceAttributes(source_id={self.source_id})"


class CronJob(Base):
    """
    Represents a scheduled cron job for an organization.
    """

    __tablename__ = "cron_jobs"
    __table_args__ = {"schema": "scheduler"}

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    organization_id = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name = mapped_column(String, nullable=False)
    cron_expr = mapped_column(String, nullable=False)
    tz = mapped_column(String, nullable=False)
    entrypoint = mapped_column(make_pg_enum(CronEntrypoint, schema="scheduler"), nullable=False)
    payload = mapped_column(JSONB, nullable=False, default=dict)
    is_enabled = mapped_column(Boolean, nullable=False, default=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    cron_runs = relationship(
        "CronRun",
        back_populates="cron_job",
        cascade="all, delete-orphan",
        order_by="CronRun.scheduled_for.desc()",
    )

    def __str__(self):
        return f"CronJob(name={self.name}, organization_id={self.organization_id})"


class CronRun(Base):
    """
    Represents an execution run of a cron job.
    """

    __tablename__ = "cron_runs"
    __table_args__ = {"schema": "scheduler"}

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    cron_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scheduler.cron_jobs.id"),
        nullable=False,
        index=True,
    )
    scheduled_for = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    started_at = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at = mapped_column(DateTime(timezone=True), nullable=True)
    status = mapped_column(make_pg_enum(CronStatus, schema="scheduler"), nullable=False)
    error = mapped_column(Text, nullable=True)
    result = mapped_column(JSONB, nullable=True)

    # Relationships
    cron_job = relationship("CronJob", back_populates="cron_runs")

    def __str__(self):
        return f"CronRun(cron_id={self.cron_id}, status={self.status}, scheduled_for={self.scheduled_for})"


class EndpointPollingHistory(Base):
    """
    Tracks processed values for endpoint polling cron jobs.
    Each row represents a value that has been processed by a specific cron job.
    """

    __tablename__ = "endpoint_polling_history"
    __table_args__ = (
        UniqueConstraint("cron_id", "tracked_value", name="uq_cron_tracked_value"),
        {"schema": "scheduler"},
    )

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    cron_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scheduler.cron_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tracked_value = mapped_column(String, nullable=False, index=True)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationship
    cron_job = relationship("CronJob", backref="endpoint_polling_history")

    def __str__(self):
        return f"EndpointPollingHistory(cron_id={self.cron_id}, tracked_value={self.tracked_value})"


class InputGroundtruth(Base):
    __tablename__ = "input_groundtruth"
    __table_args__ = (
        sa.UniqueConstraint("dataset_id", "position", name="uq_input_groundtruth_dataset_position"),
        sa.CheckConstraint("position >= 1", name="ck_input_groundtruth_position_positive"),
        {"schema": "quality_assurance"},
    )

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, server_default=func.gen_random_uuid())

    dataset_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quality_assurance.dataset_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    position = mapped_column(Integer, nullable=False)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    input = mapped_column(JSONB, nullable=False)
    groundtruth = mapped_column(String, nullable=True)

    # Relationships
    dataset = relationship("DatasetProject", back_populates="input_groundtruths")
    version_outputs = relationship("VersionOutput", back_populates="input_groundtruth", cascade="all, delete-orphan")

    def __str__(self):
        return f"InputGroundtruth(id={self.id}, input={self.input})"


class DatasetProject(Base):
    __tablename__ = "dataset_project"
    __table_args__ = {"schema": "quality_assurance"}

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, server_default=func.gen_random_uuid())
    project_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_name = mapped_column(String, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="datasets")
    input_groundtruths = relationship("InputGroundtruth", back_populates="dataset", cascade="all, delete-orphan")

    def __str__(self):
        return f"DatasetProject(id={self.id}, name={self.dataset_name})"


class VersionOutput(Base):
    __tablename__ = "version_output"
    __table_args__ = (
        sa.UniqueConstraint("input_id", "graph_runner_id", name="uq_version_output_input_graph_runner"),
        {"schema": "quality_assurance"},
    )

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, server_default=func.gen_random_uuid())
    input_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quality_assurance.input_groundtruth.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    output = mapped_column(String, nullable=False)
    graph_runner_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    input_groundtruth = relationship("InputGroundtruth", back_populates="version_outputs")
    graph_runner = relationship("GraphRunner")
    evaluations = relationship("JudgeEvaluation", back_populates="version_output", cascade="all, delete-orphan")

    def __str__(self):
        return f"VersionOutput(id={self.id}, input_id={self.input_id}, graph_runner_id={self.graph_runner_id})"


class LLMJudge(Base):
    __tablename__ = "llm_judges"
    __table_args__ = {"schema": "quality_assurance"}

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, server_default=func.gen_random_uuid())
    project_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = mapped_column(String, nullable=False)
    description = mapped_column(Text, nullable=True)
    evaluation_type = mapped_column(make_pg_enum(EvaluationType), nullable=False)
    llm_model_reference = mapped_column(String, nullable=False, default="openai:gpt-5-mini")
    prompt_template = mapped_column(Text, nullable=False)
    temperature = mapped_column(Float, nullable=True, default=1.0)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project")
    evaluations = relationship("JudgeEvaluation", back_populates="judge", cascade="all, delete-orphan")

    def __str__(self):
        return f"LLMJudge(id={self.id}, name={self.name}, evaluation_type={self.evaluation_type})"


class JudgeEvaluation(Base):
    __tablename__ = "judge_evaluations"
    __table_args__ = (
        sa.UniqueConstraint("judge_id", "version_output_id", name="uq_judge_version_output"),
        {"schema": "quality_assurance"},
    )

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, server_default=func.gen_random_uuid())
    judge_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quality_assurance.llm_judges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_output_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quality_assurance.version_output.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_result = mapped_column(JSONB, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    judge = relationship("LLMJudge", back_populates="evaluations")
    version_output = relationship("VersionOutput", back_populates="evaluations")

    def __str__(self):
        return f"JudgeEvaluation(judge_id={self.judge_id}, version_output_id={self.version_output_id})"


class LLMModel(Base):
    __tablename__ = "llm_models"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, server_default=func.gen_random_uuid())
    display_name = mapped_column(String, nullable=False)
    description = mapped_column(Text, nullable=True)
    provider = mapped_column(String, nullable=False)
    model_name = mapped_column(String, nullable=False)
    model_capacity = mapped_column(ModelCapabilityList, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    llm_cost = relationship("LLMCost", back_populates="llm_model", uselist=False, cascade="all, delete-orphan")

    def __str__(self) -> str:
        return f"LLMModel(id={self.id}, name={self.name}, provider={self.provider})"


class Cost(Base):
    __tablename__ = "costs"
    __table_args__ = {"schema": "credits"}

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    entity_type = mapped_column(make_pg_enum(EntityType), nullable=True)
    credits_per = mapped_column(JSONB, nullable=True)
    credits_per_call = mapped_column(Float, nullable=True)
    credits_per_input_token = mapped_column(Float, nullable=True)
    credits_per_output_token = mapped_column(Float, nullable=True)

    __mapper_args__ = {
        "polymorphic_on": entity_type,
    }


class LLMCost(Cost):
    __tablename__ = "llm_costs"
    __table_args__ = {"schema": "credits"}

    id = mapped_column(UUID(as_uuid=True), ForeignKey("credits.costs.id"), primary_key=True)
    llm_model_id = mapped_column(UUID(as_uuid=True), ForeignKey("llm_models.id"), unique=True)

    llm_model = relationship("LLMModel", back_populates="llm_cost")

    __mapper_args__ = {"polymorphic_identity": EntityType.LLM.value}


class ComponentCost(Cost):
    __tablename__ = "component_costs"
    __table_args__ = {"schema": "credits"}

    id = mapped_column(UUID(as_uuid=True), ForeignKey("credits.costs.id"), primary_key=True)
    component_version_id = mapped_column(UUID(as_uuid=True), ForeignKey("component_versions.id"), unique=True)

    component_version = relationship("ComponentVersion", back_populates="component_cost")

    __mapper_args__ = {"polymorphic_identity": EntityType.COMPONENT.value}


class ParameterValueCost(Cost):
    __tablename__ = "parameter_value_costs"
    __table_args__ = {"schema": "credits"}

    id = mapped_column(UUID(as_uuid=True), ForeignKey("credits.costs.id"), primary_key=True)
    component_parameter_definition_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("component_parameter_definitions.id")
    )
    parameter_value = mapped_column(String)

    __mapper_args__ = {"polymorphic_identity": EntityType.PARAMETER_VALUE.value}


class Usage(Base):
    __tablename__ = "usages"
    __table_args__ = (
        UniqueConstraint("project_id", "year", "month", name="uq_usage_project_year_month"),
        {"schema": "credits"},
    )

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    project_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year = mapped_column(Integer, nullable=False)
    month = mapped_column(Integer, nullable=False)
    credits_used = mapped_column(Float, nullable=False, default=0.0)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="usage")


class SpanUsage(Base):
    """Stores credit usage for spans that have billable usage."""

    __tablename__ = "span_usages"
    __table_args__ = {"schema": "credits"}

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    span_id = mapped_column(
        String,
        ForeignKey("traces.spans.span_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    credits_input_token = mapped_column(Float, nullable=True)
    credits_output_token = mapped_column(Float, nullable=True)
    credits_per_call = mapped_column(Float, nullable=True)
    credits_per = mapped_column(JSONB, nullable=True)

    def __str__(self):
        return (
            f"SpanUsage(span_id={self.span_id}, credits_input_token={self.credits_input_token}, "
            f"credits_output_token={self.credits_output_token}, credits_per_call={self.credits_per_call}, "
            f"credits_per={self.credits_per})"
        )


class OrganizationLimit(Base):
    """
    Tracks monthly limits for organizations.
    Allows setting different limits per organization per month.
    """

    __tablename__ = "organization_limits"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_organization_limit"),
        {"schema": "credits"},
    )

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    organization_id = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    limit = mapped_column(Float, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __str__(self):
        return f"OrganizationLimit(org={self.organization_id}, limit={self.limit})"


class Widget(Base):
    """
    Widget configuration for embeddable chat widgets.
    Each widget maps to a project and stores UI configuration.
    """

    __tablename__ = "widgets"
    __table_args__ = {"schema": "widget"}

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    widget_key = mapped_column(String(64), unique=True, nullable=False, index=True)
    project_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name = mapped_column(String(255), nullable=False)
    is_enabled = mapped_column(Boolean, default=True, nullable=False)
    config = mapped_column(
        JSONB,
        nullable=False,
        default={
            "theme": {
                "primary_color": "#6366F1",
                "secondary_color": "#4F46E5",
                "background_color": "#FFFFFF",
                "text_color": "#1F2937",
                "border_radius": 12,
                "font_family": "Inter, system-ui, sans-serif",
                "logo_url": None,
            },
            "first_messages": [],
            "suggestions": [],
            "placeholder_text": "Type a message...",
            "powered_by_visible": True,
        },
    )
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship(
        "Project",
        backref="widgets",
        primaryjoin="Widget.project_id == Project.id",
        foreign_keys="[Widget.project_id]",
    )

    def __str__(self):
        return f"Widget(id={self.id}, name={self.name}, project_id={self.project_id})"
