from uuid import UUID


class CategoryNotFound(Exception):
    def __init__(self, category_id: UUID):
        self.category_id = category_id
        super().__init__(f"Category not found: {category_id}")


class DuplicateCategoryName(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Category with name '{name}' already exists")


class InvalidCategoryUpdate(Exception):
    def __init__(self):
        super().__init__("At least one field (name or description) must be provided for update")


class ComponentNotFound(Exception):
    def __init__(self, component_id):
        self.component_id = component_id
        super().__init__(f"Component not found: {component_id}")


class EntityInUseDeletionError(Exception):
    """Raised when attempting to delete an entity that is currently in use by instances."""

    def __init__(self, entity_id: UUID, instance_count: int, entity_type: str = "entity"):
        self.entity_id = entity_id
        self.instance_count = instance_count
        self.entity_type = entity_type
        super().__init__(
            f"Cannot delete {entity_type} {entity_id}: it is currently used by {instance_count} instance(s)"
        )


class ComponentVersionMismatchError(Exception):
    def __init__(self, component_version_id: UUID, expected_component_id: UUID, actual_component_id: UUID):
        self.component_version_id = component_version_id
        self.expected_component_id = expected_component_id
        self.actual_component_id = actual_component_id
        super().__init__(
            f"Component version {component_version_id} does not belong to component {expected_component_id}. "
            f"It belongs to component {actual_component_id}"
        )


class InvalidReleaseStageUpdate(Exception):
    def __init__(self, component_id, message: str | None = None):
        detail = message or "Invalid release stage update request"
        self.component_id = component_id
        super().__init__(f"{detail} for component: {component_id}")


class ProjectNotFound(Exception):
    def __init__(self, project_id: UUID):
        self.project_id = project_id
        super().__init__(f"Project not found: {project_id}")


class GraphNotFound(Exception):
    def __init__(self, graph_id: UUID):
        self.graph_id = graph_id
        super().__init__(f"Graph not found: {graph_id}")


class EnvironmentNotFound(Exception):
    def __init__(self, project_id: UUID, environment: str):
        self.project_id = project_id
        self.environment = environment
        super().__init__(f"Environment '{environment}' not found for project: {project_id}")


class LLMJudgeNotFound(Exception):
    def __init__(self, judge_id: UUID, project_id: UUID):
        self.judge_id = judge_id
        self.project_id = project_id
        super().__init__(f"LLM judge {judge_id} not found in project {project_id}")


class SourceNotFound(Exception):
    def __init__(self, source_id: UUID):
        self.source_id = source_id
        super().__init__(f"Source not found: {source_id}")


class InvalidAgentTemplate(Exception):
    def __init__(self, template_project_id: UUID, template_graph_runner_id: UUID):
        self.template_project_id = template_project_id
        self.template_graph_runner_id = template_graph_runner_id
        super().__init__(
            (
                f"Template {template_project_id} with graph runner {template_graph_runner_id} "
                "does not contain an AI agent component"
            )
        )


class ChunkSourceMismatchError(Exception):
    def __init__(self, chunk_id: str, source_id: UUID):
        self.chunk_id = chunk_id
        self.source_id = source_id
        super().__init__(f"Chunk {chunk_id} does not belong to source {source_id}")


class LLMModelNotFound(Exception):
    def __init__(self, llm_model_id: UUID):
        self.llm_model_id = llm_model_id
        super().__init__(f"LLM model not found: {llm_model_id}")


class ComponentVersionCostNotFound(Exception):
    def __init__(self, component_version_id: UUID):
        self.component_version_id = component_version_id
        super().__init__(f"Component version cost not found: {component_version_id}")


class OrganizationLimitNotFound(Exception):
    def __init__(self, id: UUID, organization_id: UUID):
        self.id = id
        self.organization_id = organization_id
        super().__init__(f"Organization limit not found: {id} for organization {organization_id}")


class OrganizationLimitExceededError(Exception):
    """Raised when an organization has reached or exceeded its monthly credit limit."""

    def __init__(self, organization_id: UUID, limit: float, current_usage: float):
        self.organization_id = organization_id
        self.limit = limit
        self.current_usage = current_usage
        super().__init__(
            f"Organization has reached its monthly credit limit. "
            f"Limit: {limit} credits, Current usage: {current_usage} credits"
        )


class MissingDataSourceError(Exception):
    """Raised when a component requires a data source but none is configured."""

    def __init__(self, component_name: str | None = None):
        self.component_name = component_name
        if component_name:
            message = (
                f"The component '{component_name}' requires a data source to be configured. "
                "Please select a data source in the component settings before running the agent."
            )
        else:
            message = (
                "A component requires a data source to be configured. "
                "Please select a data source in the component settings before running the agent."
            )
        super().__init__(message)


class GraphNotBoundToProjectError(Exception):
    """Raised when a graph is not bound to the expected project."""

    def __init__(
        self, graph_runner_id: UUID, bound_project_id: UUID | None = None, expected_project_id: UUID | None = None
    ):
        self.graph_runner_id = graph_runner_id
        self.bound_project_id = bound_project_id
        self.expected_project_id = expected_project_id
        if bound_project_id is None:
            message = f"Graph with ID {graph_runner_id} is not bound to any project."
        else:
            message = (
                f"Graph with ID {graph_runner_id} is bound to project {bound_project_id}, not {expected_project_id}."
            )
        super().__init__(message)


class GraphVersionSavingFromNonDraftError(Exception):
    """Raised when attempting to save a version from a graph runner that is not in DRAFT environment."""

    def __init__(self, graph_runner_id: UUID, current_environment: str):
        self.graph_runner_id = graph_runner_id
        self.current_environment = current_environment
        super().__init__(
            f"Can only save versions from DRAFT. Graph runner {graph_runner_id} "
            f"is currently in environment: {current_environment}"
        )


class WidgetNotFound(Exception):
    def __init__(self, widget_id: UUID | None = None, widget_key: str | None = None):
        if widget_id:
            super().__init__(f"Widget with id {widget_id} not found")
        elif widget_key:
            super().__init__(f"Widget with key {widget_key} not found")
        else:
            super().__init__("Widget not found")


class WidgetDisabled(Exception):
    def __init__(self, widget_key: str):
        super().__init__(f"Widget {widget_key} is disabled")


class GraphRunnerAlreadyInEnvironmentError(Exception):
    def __init__(self, graph_runner_id: UUID, environment: str):
        self.graph_runner_id = graph_runner_id
        self.environment = environment
        super().__init__(f"Graph runner {graph_runner_id} is already in {environment}")


class MissingIntegrationError(Exception):
    """Raised when a component instance requires an integration but none is configured."""

    def __init__(self, integration_name: str, integration_service: str, component_instance_name: str):
        self.integration_name = integration_name
        self.integration_service = integration_service
        self.component_instance_name = component_instance_name
        super().__init__(
            f"Please add integration {integration_name}:{integration_service} "
            f"for component instance {component_instance_name}"
        )


class OAuthConnectionNotFoundError(Exception):
    """Raised when an OAuth connection is not found."""

    def __init__(
        self,
        connection_id: UUID | None = None,
        project_id: UUID | None = None,
        provider: str | None = None,
    ):
        self.connection_id = connection_id
        self.project_id = project_id
        self.provider = provider
        if connection_id:
            message = f"OAuth connection {connection_id} not found"
        elif project_id and provider:
            message = f"No OAuth connection found for project {project_id} and provider {provider}"
        else:
            message = "OAuth connection not found"
        super().__init__(message)


class OAuthConnectionUnauthorizedError(Exception):
    """Raised when attempting to access an OAuth connection that doesn't belong to the project."""

    def __init__(self, connection_id: UUID, project_id: UUID):
        self.connection_id = connection_id
        self.project_id = project_id
        super().__init__(f"OAuth connection {connection_id} does not belong to project {project_id}")


class NangoConnectionNotFoundError(Exception):
    """Raised when a connection is not found in Nango (OAuth flow incomplete)."""

    def __init__(self, project_id: UUID, provider: str):
        self.project_id = project_id
        self.provider = provider
        super().__init__(
            f"Connection not found in Nango for project {project_id}, provider {provider}. "
            "OAuth flow may not be complete."
        )


class NangoTokenMissingError(Exception):
    """Raised when access token is not found in Nango credentials."""

    def __init__(self, connection_id: UUID):
        self.connection_id = connection_id
        super().__init__(
            f"Access token not found in Nango credentials for connection {connection_id}",
        )
