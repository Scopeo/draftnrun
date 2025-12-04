import json
from enum import StrEnum
from typing import Any
from logging import getLogger
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from fastapi import FastAPI
from wtforms import StringField, Form
from wtforms.validators import DataRequired, ValidationError
from starlette.requests import Request

from ada_backend.database.setup_db import engine
from ada_backend.database import models as db
from settings import settings


LOGGER = getLogger(__name__)


class AdminCategory(StrEnum):
    PROJECTS = "Projects"
    COMPONENTS = "Components"
    SOURCES = "Data Sources"
    SCHEDULER = "Scheduler"
    QUALITY_ASSURANCE = "Quality Assurance"
    LLM_MODELS = "LLM Models"
    CREDITS = "Credits"


class EnhancedModelView(ModelView):
    """
    A base class for enhanced admin views with support for relationship fields.
    """

    can_view_details = True
    can_edit = True
    can_create = True
    can_delete = True
    column_default_sort = "id"
    column_display_pk = True
    form_excluded_columns = ["created_at", "updated_at"]


# --- Admin Views ---
class CronJobAdmin(EnhancedModelView, model=db.CronJob):
    category = AdminCategory.SCHEDULER
    icon = "fas fa-clock"
    column_list = [
        "id",
        "name",
        "organization_id",
        "cron_expr",
        "tz",
        "entrypoint",
        "payload",
        "is_enabled",
        "created_at",
        "updated_at",
        "deleted_at",
    ]
    column_searchable_list = ["name", "entrypoint"]
    column_filters = ["is_enabled", "organization_id", "entrypoint"]
    form_columns = [
        "name",
        "organization_id",
        "cron_expr",
        "tz",
        "entrypoint",
        "payload",
        "is_enabled",
    ]


class CronRunAdmin(EnhancedModelView, model=db.CronRun):
    category = AdminCategory.SCHEDULER
    icon = "fas fa-history"
    column_list = [
        "id",
        "cron_job",
        "status",
        "scheduled_for",
        "started_at",
        "finished_at",
        "error",
        "result",
    ]
    column_searchable_list = ["cron_job.name"]
    column_filters = ["status"]
    can_create = False
    can_edit = False


class EndpointPollingHistoryAdmin(EnhancedModelView, model=db.EndpointPollingHistory):
    category = AdminCategory.SCHEDULER
    icon = "fas fa-list-check"
    column_list = [
        "id",
        "cron_job",
        "tracked_value",
        "created_at",
    ]
    column_searchable_list = ["tracked_value", "cron_job.name"]
    column_filters = ["cron_job"]
    can_create = False
    can_edit = False
    column_default_sort = ("created_at", True)  # Sort by created_at descending


class ProjectAdmin(EnhancedModelView, model=db.Project):
    category = AdminCategory.PROJECTS
    icon = "fas fa-users"
    column_list = [
        "id",
        "name",
        "description",
        "type",
        "organization_id",
        "created_at",
        "updated_at",
    ]


class ProjectEnvironmentBinding(EnhancedModelView, model=db.ProjectEnvironmentBinding):
    category = AdminCategory.PROJECTS
    icon = "fas fa-link"
    column_list = ["id", "project", "environment", "graph_runner", "created_at", "updated_at"]
    form_excluded_columns = ["created_at", "updated_at"]


class IntegrationAdmin(EnhancedModelView, model=db.Integration):
    category = AdminCategory.PROJECTS
    icon = "fas fa-plug"
    column_list = ["id", "name", "service"]


class SecretIntegrationAdmin(EnhancedModelView, model=db.SecretIntegration):
    category = AdminCategory.PROJECTS
    icon = "fas fa-plug"
    column_list = [
        "id",
        "integration",
        "encrypted_access_token",
        "encrypted_refresh_token",
        "expires_in",
        "token_last_updated",
    ]


class IntegrationComponentInstanceRelationshipAdmin(
    EnhancedModelView, model=db.IntegrationComponentInstanceRelationship
):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-plug"
    column_list = ["id", "secret_integration", "component_instance", "created_at", "updated_at"]


class OrganizationSecretAdmin(EnhancedModelView, model=db.OrganizationSecret):
    category = AdminCategory.PROJECTS
    icon = "fas fa-key"
    column_list = ["id", "organization_id", "key", "encrypted_secret", "created_at", "updated_at"]
    form_excluded_columns = ["encrypted_secret", "created_at", "updated_at"]

    async def on_model_change(
        self,
        data: dict,
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        """
        Encrypt the secret before saving to the database.
        """
        if secret := data.get("secret"):
            model.set_secret(secret)

    async def scaffold_form(self, rules=None):
        """
        Customize the form to include fields for the non-encrypted secret and project.
        """
        form_class = await super().scaffold_form(rules)
        form_class.secret = StringField(
            "Secret", description="Enter the non-encrypted secret", validators=[DataRequired()]
        )
        return form_class


class ComponentParameterDefinitionAdmin(EnhancedModelView, model=db.ComponentParameterDefinition):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cog"
    column_list = [
        "id",
        "component_version",
        "name",
        "type",
        "nullable",
        "default",
        "ui_component",
        "is_advanced",
        "parameter_group",
        "parameter_order_within_group",
        "model_capabilities",
    ]
    form_columns = [
        "component_version",
        "name",
        "type",
        "nullable",
        "default",
        "ui_component",
        "ui_component_properties",
        "is_advanced",
        "parameter_group",
        "parameter_order_within_group",
    ]
    column_filters = ["type", "is_advanced", "nullable", "ui_component", "parameter_group"]
    column_searchable_list = ["name", "component_version.component.name", "parameter_group.name"]


class ComponentAdmin(EnhancedModelView, model=db.Component):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cubes"
    column_list = [
        "id",
        "name",
        "is_agent",
        "function_callable",
        "can_use_function_calling",
        "is_protected",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["name", "is_agent"]


class ComponentVersionAdmin(EnhancedModelView, model=db.ComponentVersion):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cubes"
    column_list = [
        "id",
        "component",
        "version_tag",
        "description",
        "release_stage",
        "default_tool_description",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["version_tag", "description", "release_stage"]
    form_columns = ["component", "version_tag", "description", "release_stage"]


class ReleaseStageToCurrentVersionMappingAdmin(EnhancedModelView, model=db.ReleaseStageToCurrentVersionMapping):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cubes"
    column_list = [
        "id",
        "component_version.component",
        "release_stage",
        "component_version",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["component_version.component.name", "release_stage"]
    form_columns = ["component_version", "release_stage"]


class ComponentCategoryAdmin(EnhancedModelView, model=db.ComponentCategory):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-tags"
    column_list = ["id", "component", "category", "created_at", "updated_at"]
    form_columns = ["component", "category"]

    column_searchable_list = [
        "category.name",
    ]


class CategoryAdmin(EnhancedModelView, model=db.Category):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-tags"
    column_list = ["id", "name", "description", "created_at", "updated_at"]
    form_columns = ["name", "description"]


class GraphRunnerAdmin(EnhancedModelView, model=db.GraphRunner):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cubes"
    column_list = ["id", "created_at", "updated_at", "tag_version", "version_name", "change_log"]


class ComponentInstanceAdmin(EnhancedModelView, model=db.ComponentInstance):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cogs"
    column_list = ["id", "component_version", "name", "ref", "tool_description", "created_at"]
    column_searchable_list = ["ref", "id"]
    form_columns = ["component_version", "ref", "tool_description"]


class GraphRunnerNodeAdmin(EnhancedModelView, model=db.GraphRunnerNode):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cogs"
    column_list = ["id", "node_id", "graph_runner_id", "node_type", "is_start_node", "created_at", "updated_at"]


class GraphRunnerEdgeAdmin(EnhancedModelView, model=db.GraphRunnerEdge):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cogs"
    column_list = ["id", "source_node_id", "target_node_id", "order", "graph_runner_id", "created_at", "updated_at"]


class ComponentParameterChildRelationshipAdmin(EnhancedModelView, model=db.ComponentParameterChildRelationship):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-cogs"
    column_list = [
        "id",
        "component_parameter_definition_id",
        "child_component_id",
    ]


class ParameterGroupAdmin(EnhancedModelView, model=db.ParameterGroup):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-layer-group"
    column_list = [
        "id",
        "name",
    ]
    form_columns = [
        "name",
    ]
    column_searchable_list = ["name"]


class ComponentParameterGroupAdmin(EnhancedModelView, model=db.ComponentParameterGroup):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-layer-group"
    column_list = [
        "id",
        "component_version",
        "parameter_group",
        "group_order_within_component",
    ]
    form_columns = [
        "component_version",
        "parameter_group",
        "group_order_within_component",
    ]
    column_searchable_list = ["component_version.component.name", "parameter_group.name"]


class BasicParameterAdmin(EnhancedModelView, model=db.BasicParameter):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-sliders-h"
    column_list = [
        "id",
        "component_instance",
        "parameter_definition",
        "value",
        "organization_secret",
        "order",
    ]
    form_columns = [
        "component_instance",
        "parameter_definition",
        "value",
        "organization_secret",
        "order",
    ]
    column_filters = [
        "parameter_definition.name",
    ]

    column_searchable_list = [
        "parameter_definition.name",
    ]


class ComponentSubInputAdmin(EnhancedModelView, model=db.ComponentSubInput):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-network-wired"
    column_list = [
        "id",
        "parent_component_instance",
        "child_component_instance",
        "parameter_definition",
        "order",
    ]
    form_columns = [
        "parent_component_instance",
        "child_component_instance",
        "parameter_definition",
        "order",
    ]


class ToolDescriptionForm(Form):
    name = StringField("Name")
    description = StringField("Description")
    tool_properties = StringField("Tool Properties", default="{}", validators=[DataRequired()])
    required_tool_properties = StringField("Required Properties", default="[]", validators=[DataRequired()])


class ToolDescriptionAdmin(EnhancedModelView, model=db.ToolDescription):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-wrench"
    column_list = [
        "id",
        "name",
        "description",
        "tool_properties",
        "required_tool_properties",
        "created_at",
        "updated_at",
    ]

    form = ToolDescriptionForm

    async def on_model_change(
        self,
        data: dict,
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        fields_with_errors = []
        try:
            data["tool_properties"] = json.loads(data["tool_properties"])
        except json.JSONDecodeError:
            fields_with_errors.append("tool_properties")
        try:
            data["required_tool_properties"] = json.loads(data["required_tool_properties"])
        except json.JSONDecodeError:
            fields_with_errors.append("required_tool_properties")
        if fields_with_errors:
            raise ValidationError(f"Invalid JSON format for fields: {fields_with_errors}")
        await super().on_model_change(data, model, is_created, request)


class ApiKeyAdmin(EnhancedModelView, model=db.ApiKey):
    category = AdminCategory.PROJECTS
    icon = "fas fa-key"
    column_list = [
        "id",
        "name",
        "is_active",
        "project_id",
        "public_key",
        "creator_user_id",
        "revoker_user_id",
        "created_at",
        "updated_at",
    ]

    column_searchable_list = ["public_key", "name"]
    column_filters = ["is_active", "project_id", "creator_user_id"]

    form_columns = ["public_key", "name", "is_active", "project_id", "creator_user_id", "revoker_user_id"]


class IngestionTaskAdmin(EnhancedModelView, model=db.IngestionTask):
    category = AdminCategory.SOURCES
    icon = "fas fa-cogs"
    column_list = [
        "id",
        "source_id",
        "organization_id",
        "source_name",
        "source_type",
        "status",
        "created_at",
        "updated_at",
    ]

    column_filters = ["source_name", "source_type", "status", "organization_id"]


class SourceAdmin(EnhancedModelView, model=db.DataSource):
    category = AdminCategory.SOURCES
    icon = "fas fa-database"
    column_list = [
        "id",
        "name",
        "type",
        "organization_id",
        "database_schema",
        "database_table_name",
        "qdrant_collection_name",
        "qdrant_schema",
        "embedding_model_reference",
        "created_at",
        "updated_at",
        "last_ingestion_time",
    ]

    column_searchable_list = ["organization_id", "type"]
    column_filters = ["id", "database_schema"]

    form_columns = [
        "name",
        "type",
        "organization_id",
        "database_schema",
        "database_table_name",
        "qdrant_collection_name",
        "qdrant_schema",
        "embedding_model_reference",
    ]


class SourceAttributesAdmin(EnhancedModelView, model=db.SourceAttributes):
    category = AdminCategory.SOURCES
    icon = "fas fa-database"
    column_list = [
        "id",
        "source_id",
        "created_at",
        "updated_at",
    ]


class PortDefinitionAdmin(EnhancedModelView, model=db.PortDefinition):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-plug"
    column_list = [
        "id",
        "component",
        "name",
        "port_type",
        "is_canonical",
        "description",
    ]
    column_searchable_list = ["name", "description"]
    column_filters = ["port_type", "is_canonical", "component.name"]
    form_columns = [
        "component",
        "name",
        "port_type",
        "is_canonical",
        "description",
    ]


class PortMappingAdmin(EnhancedModelView, model=db.PortMapping):
    category = AdminCategory.COMPONENTS
    icon = "fas fa-network-wired"
    column_list = [
        "id",
        "graph_runner",
        "source_instance",
        "source_port_definition",
        "target_instance",
        "target_port_definition",
        "dispatch_strategy",
    ]
    column_searchable_list = ["dispatch_strategy"]
    column_filters = ["dispatch_strategy", "graph_runner.id"]
    form_columns = [
        "graph_runner",
        "source_instance",
        "source_port_definition",
        "target_instance",
        "target_port_definition",
        "dispatch_strategy",
    ]


class LLMJudgeAdmin(EnhancedModelView, model=db.LLMJudge):
    category = AdminCategory.QUALITY_ASSURANCE
    icon = "fas fa-balance-scale"
    column_list = [
        "id",
        "project_id",
        "name",
        "description",
        "evaluation_type",
        "llm_model_reference",
        "prompt_template",
        "temperature",
        "created_at",
        "updated_at",
    ]
    column_searchable_list = ["name", "description", "llm_model_reference"]
    form_columns = [
        "project_id",
        "name",
        "description",
        "evaluation_type",
        "llm_model_reference",
        "prompt_template",
        "temperature",
    ]


class LLMModelsAdmin(EnhancedModelView, model=db.LLMModel):
    category = AdminCategory.LLM_MODELS
    name = "LLM Model"
    icon = "fas fa-cogs"
    column_list = [
        "id",
        "display_name",
        "description",
        "provider",
        "model_name",
        "model_capacity",
        "created_at",
        "updated_at",
    ]
    form_columns = ["display_name", "provider", "model_name", "model_capacity"]

    column_searchable_list = ["display_name", "provider", "model_name"]
    column_filters = ["provider", "model_name"]


class CreditAdmin(EnhancedModelView, model=db.Cost):
    category = AdminCategory.CREDITS
    icon = "fas fa-money-bill"
    column_list = [
        "id",
        "entity_type",
        "credits_per_unit",
        "credits_per_call",
        "credits_per_input_token",
        "credits_per_output_token",
    ]
    form_columns = [
        "entity_type",
        "credits_per_unit",
        "credits_per_call",
        "credits_per_input_token",
        "credits_per_output_token",
    ]
    column_filters = ["entity_type"]
    column_searchable_list = ["entity_type"]


class UsageAdmin(EnhancedModelView, model=db.Usage):
    category = AdminCategory.CREDITS
    icon = "fas fa-money-bill"
    column_list = [
        "id",
        "project_id",
        "year",
        "month",
        "credits_used",
    ]
    form_columns = [
        "project_id",
        "year",
        "month",
        "credits_used",
    ]
    column_filters = ["project_id", "year", "month"]
    column_searchable_list = ["project_id", "year", "month"]


class AdminAuth(AuthenticationBackend):
    """Basic username/password authentication for admin interface."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        valid_username = settings.ADMIN_USERNAME
        valid_password = settings.ADMIN_PASSWORD

        if username == valid_username and password == valid_password:
            request.session.update({"authenticated": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("authenticated", False)


def setup_admin(app: FastAPI):
    """
    Set up the SQLAdmin views for the application.
    """
    if not settings.BACKEND_SECRET_KEY:
        raise ValueError("BACKEND_SECRET_KEY is not set")
    authentication_backend = AdminAuth(secret_key=settings.BACKEND_SECRET_KEY)
    admin = Admin(
        app,
        engine,
        title="Draft'n run Agents Admin",
        authentication_backend=authentication_backend,
    )

    # Add views to the admin interface
    admin.add_view(ProjectAdmin)
    admin.add_view(ProjectEnvironmentBinding)
    admin.add_view(OrganizationSecretAdmin)
    admin.add_view(ApiKeyAdmin)
    admin.add_view(SecretIntegrationAdmin)
    admin.add_view(IntegrationAdmin)
    admin.add_view(IntegrationComponentInstanceRelationshipAdmin)

    admin.add_view(GraphRunnerAdmin)
    admin.add_view(ComponentAdmin)
    admin.add_view(ComponentVersionAdmin)
    admin.add_view(ReleaseStageToCurrentVersionMappingAdmin)
    admin.add_view(CategoryAdmin)
    admin.add_view(ComponentCategoryAdmin)
    admin.add_view(GraphRunnerNodeAdmin)
    admin.add_view(GraphRunnerEdgeAdmin)
    admin.add_view(ComponentParameterDefinitionAdmin)
    admin.add_view(ComponentParameterChildRelationshipAdmin)
    admin.add_view(ParameterGroupAdmin)
    admin.add_view(ComponentParameterGroupAdmin)
    admin.add_view(ComponentInstanceAdmin)
    admin.add_view(BasicParameterAdmin)
    admin.add_view(ComponentSubInputAdmin)
    admin.add_view(ToolDescriptionAdmin)
    admin.add_view(SourceAdmin)
    admin.add_view(IngestionTaskAdmin)
    admin.add_view(SourceAttributesAdmin)
    admin.add_view(PortDefinitionAdmin)
    admin.add_view(PortMappingAdmin)
    admin.add_view(CronJobAdmin)
    admin.add_view(CronRunAdmin)
    admin.add_view(EndpointPollingHistoryAdmin)
    admin.add_view(LLMJudgeAdmin)
    admin.add_view(LLMModelsAdmin)
    admin.add_view(CreditAdmin)
    admin.add_view(UsageAdmin)

    return admin
