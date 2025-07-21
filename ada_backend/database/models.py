import uuid
import json
from typing import List, Optional, Union, Type
from enum import StrEnum
import logging

from sqlalchemy import (
    String,
    Text,
    JSON,
    Integer,
    ForeignKey,
    DateTime,
    Boolean,
    Enum as SQLAlchemyEnum,
    func,
    CheckConstraint,
    UUID,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, declarative_base, mapped_column
from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, Field

from ada_backend.database.utils import camel_to_snake
from settings import settings

Base = declarative_base()
LOGGER = logging.getLogger(__name__)

if not settings.FERNET_KEY:
    raise ValueError(
        "FERNET_KEY is not set in the environment. It is required for secure storage.",
    )
CIPHER = Fernet(settings.FERNET_KEY)


def make_pg_enum(enum_cls: Type[StrEnum]) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum_cls,
        name=camel_to_snake(enum_cls.__name__),
        values_callable=lambda x: [e.value for e in x],
        native_enum=True,
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


class OrgSecretType(StrEnum):
    LLM_API_KEY = "llm_api_key"
    PASSWORD = "password"


class ApiKeyType(StrEnum):
    PROJECT = "project"
    ORGANIZATION = "organization"


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


class SourceType(StrEnum):
    """Enumeration of source types."""

    GOOGLE_DRIVE = "google_drive"
    LOCAL = "local"
    DATABASE = "database"


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


class CronStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    RUNNING = "running"


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


def cast_value(
    parameter_type: ParameterType,
    unresolved_value: str,
) -> str | int | float | bool | dict:
    if parameter_type != ParameterType.STRING and (unresolved_value == "None" or unresolved_value is None):
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
    elif parameter_type == ParameterType.COMPONENT:
        raise ValueError("Parameter type COMPONENT is not supported for BasicParameters")
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
    description = mapped_column(Text, nullable=True)
    is_agent = mapped_column(Boolean, nullable=False, default=False)
    integration_id = mapped_column(UUID(as_uuid=True), ForeignKey("integrations.id"), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    function_callable = mapped_column(Boolean, nullable=False, default=False)
    can_use_function_calling = mapped_column(Boolean, nullable=False, default=False)
    is_protected = mapped_column(Boolean, nullable=False, default=False)
    release_stage = mapped_column(make_pg_enum(ReleaseStage), nullable=False, default=ReleaseStage.BETA)
    default_tool_description_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_descriptions.id"),
        nullable=True,
    )
    default_tool_description = relationship("ToolDescription", foreign_keys=[default_tool_description_id])
    definitions = relationship(
        "ComponentParameterDefinition",
        back_populates="component",
    )
    child_definitions = relationship("ComponentParameterChildRelationship", back_populates="child_component")
    categories = relationship(
        "ComponentCategory",
        back_populates="component",
        cascade="all, delete-orphan",
    )

    def __str__(self):
        return f"Component({self.name})"


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

    graph_edges = relationship("GraphRunnerEdge", back_populates="graph_runner")
    nodes = relationship("GraphRunnerNode", back_populates="graph_runner")

    def __str__(self):
        return f"Graph Runner({self.id})"


class ComponentParameterDefinition(Base):
    """
    Defines the parameters that a component can accept, including subinputs.
    """

    __tablename__ = "component_parameter_definitions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
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

    component = relationship("Component", back_populates="definitions")
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
    child_component_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )

    component_parameter_definition = relationship("ComponentParameterDefinition", back_populates="child_components")
    child_component = relationship("Component", back_populates="child_definitions")

    def __str__(self):
        return (
            f"CompParamToChildCompRel(component_parameter_definition_id={self.component_parameter_definition_id}, "
            f"child_component_id={self.child_component_id})"
        )


class ComponentInstance(Base):
    """Configured instances of components."""

    __tablename__ = "component_instances"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    component_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = mapped_column(String, nullable=True, index=True)
    ref = mapped_column(String, nullable=True, index=True)
    tool_description_id = mapped_column(UUID(as_uuid=True), ForeignKey("tool_descriptions.id"), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    component = relationship("Component")
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
    relationships = relationship(
        "IntegrationComponentInstanceRelationship",
        back_populates="component_instance",
        cascade="all, delete-orphan",
    )

    def __str__(self):
        return f"ComponentInstance(ref={self.ref})"


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


class ToolDescription(Base):
    """Defines metadata for tools used in OpenAI function calling."""

    __tablename__ = "tool_descriptions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = mapped_column(String, unique=True, nullable=False)
    description = mapped_column(Text, nullable=False)
    tool_properties = mapped_column(JSON, nullable=True, default=dict)
    required_tool_properties = mapped_column(JSON, nullable=True, default=list)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __str__(self):
        return f"ToolDescription({self.name})"


class Project(Base):
    """
    Tracks projects, which are collections of components and their configurations.
    """

    __tablename__ = "projects"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = mapped_column(String, unique=False, nullable=False)
    description = mapped_column(Text, nullable=True)
    organization_id = mapped_column(UUID(as_uuid=True), nullable=False)
    companion_image_url = mapped_column(String, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    api_keys = relationship(
        "ProjectApiKey",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    envs = relationship("ProjectEnvironmentBinding", back_populates="project")

    def __str__(self):
        return f"Project({self.name})"


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
    entrypoint = mapped_column(make_pg_enum(CronEntrypoint), nullable=False)
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
    status = mapped_column(make_pg_enum(CronStatus), nullable=False)
    error = mapped_column(Text, nullable=True)
    result = mapped_column(JSONB, nullable=True)

    # Relationships
    cron_job = relationship("CronJob", back_populates="cron_runs")

    def __str__(self):
        return f"CronRun(cron_id={self.cron_id}, status={self.status}, scheduled_for={self.scheduled_for})"

class QuestionsAnswers(Base):
    __tablename__ = "questions_answers"
    __table_args__ = {"schema": "evaluations"}  # Specify the evaluations schema

    id = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, server_default=func.gen_random_uuid())

    organization_id = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    question = mapped_column(String, nullable=False)
    groundtruth = mapped_column(String, nullable=False)

    def __str__(self):
        return f"QuestionsAnswers(id={self.id})"
