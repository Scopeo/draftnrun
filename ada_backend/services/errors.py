from uuid import UUID


class ServiceError(Exception):
    status_code: int = 500
    _safe_detail: str | None = None

    @property
    def detail(self) -> str:
        if self.status_code >= 500:
            return self._safe_detail or "An internal error occurred."
        return str(self)


class CategoryNotFound(ServiceError):
    status_code = 404

    def __init__(self, category_id: UUID):
        self.category_id = category_id
        super().__init__(f"Category not found: {category_id}")


class DuplicateCategoryName(ServiceError):
    status_code = 409

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Category with name '{name}' already exists")


class InvalidCategoryUpdate(ServiceError):
    status_code = 400

    def __init__(self):
        super().__init__("At least one field (name or description) must be provided for update")


class ComponentNotFound(ServiceError):
    status_code = 404

    def __init__(self, component_id):
        self.component_id = component_id
        super().__init__(f"Component not found: {component_id}")


class EntityInUseDeletionError(ServiceError):
    """Raised when attempting to delete an entity that is currently in use by instances."""
    status_code = 409

    def __init__(self, entity_id: UUID, instance_count: int, entity_type: str = "entity"):
        self.entity_id = entity_id
        self.instance_count = instance_count
        self.entity_type = entity_type
        super().__init__(
            f"Cannot delete {entity_type} {entity_id}: it is currently used by {instance_count} instance(s)"
        )


class ComponentVersionMismatchError(ServiceError):
    status_code = 400

    def __init__(self, component_version_id: UUID, expected_component_id: UUID, actual_component_id: UUID):
        self.component_version_id = component_version_id
        self.expected_component_id = expected_component_id
        self.actual_component_id = actual_component_id
        super().__init__(
            f"Component version {component_version_id} does not belong to component {expected_component_id}. "
            f"It belongs to component {actual_component_id}"
        )


class InvalidReleaseStageUpdate(ServiceError):
    status_code = 400

    def __init__(self, component_id, message: str | None = None):
        detail = message or "Invalid release stage update request"
        self.component_id = component_id
        super().__init__(f"{detail} for component: {component_id}")


class ProjectNotFound(ServiceError):
    status_code = 404

    def __init__(self, project_id: UUID):
        self.project_id = project_id
        super().__init__(f"Project not found: {project_id}")


class ProjectNotInOrganization(ServiceError):
    status_code = 404

    def __init__(self, project_id: UUID, organization_id: UUID):
        self.project_id = project_id
        self.organization_id = organization_id
        super().__init__(f"Project {project_id} does not belong to organization {organization_id}")


class RunNotFound(ServiceError):
    status_code = 404

    def __init__(self, run_id: UUID):
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id}")


class RunResultNotFound(ServiceError):
    """Raised when a run has no result (result_id missing or result not yet available)."""
    status_code = 404

    def __init__(self, run_id: UUID):
        self.run_id = run_id
        super().__init__(f"Run has no result: {run_id}")


class ResultsBucketNotConfigured(ServiceError):
    """Raised when RESULTS_S3_BUCKET_NAME is not set but run result storage is required."""
    status_code = 503
    _safe_detail = "Results bucket not configured"

    def __init__(self):
        super().__init__("Results bucket not configured")


class InvalidRunStatusTransition(ServiceError):
    """Raised when updating a run to a status that would go backwards (e.g. RUNNING -> PENDING)."""
    status_code = 400

    def __init__(self, current_status: str, new_status: str):
        self.current_status = current_status
        self.new_status = new_status
        super().__init__(
            f"Invalid run status transition: cannot go from {current_status} to "
            f"{new_status} (status cannot go backwards)"
        )


class ApiKeyAccessDenied(ServiceError):
    status_code = 403

    def __init__(self, resource_type: str = "resource"):
        self.resource_type = resource_type
        super().__init__(f"You don't have access to this {resource_type}")


class InvalidApiKey(ServiceError):
    status_code = 401

    def __init__(self):
        super().__init__("Invalid API key")


class GraphNotFound(ServiceError):
    status_code = 404

    def __init__(self, graph_id: UUID):
        self.graph_id = graph_id
        super().__init__(f"Graph not found: {graph_id}")


class EnvironmentNotFound(ServiceError):
    status_code = 404

    def __init__(self, project_id: UUID, environment: str):
        self.project_id = project_id
        self.environment = environment
        super().__init__(f"Environment '{environment}' not found for project: {project_id}")


class LLMJudgeNotFound(ServiceError):
    status_code = 404

    def __init__(self, judge_id: UUID, organization_id: UUID | None = None):
        self.judge_id = judge_id
        self.organization_id = organization_id
        if organization_id is not None:
            super().__init__(f"LLM judge {judge_id} not found in organization {organization_id}")
        else:
            super().__init__(f"LLM judge {judge_id} not found")


class SourceNotFound(ServiceError):
    status_code = 404

    def __init__(self, source_id: UUID):
        self.source_id = source_id
        super().__init__(f"Source not found: {source_id}")


class InvalidAgentTemplate(ServiceError):
    status_code = 400

    def __init__(self, template_project_id: UUID, template_graph_runner_id: UUID):
        self.template_project_id = template_project_id
        self.template_graph_runner_id = template_graph_runner_id
        super().__init__(
            (
                f"Template {template_project_id} with graph runner {template_graph_runner_id} "
                "does not contain an AI agent component"
            )
        )


class ChunkSourceMismatchError(ServiceError):
    status_code = 400

    def __init__(self, chunk_id: str, source_id: UUID):
        self.chunk_id = chunk_id
        self.source_id = source_id
        super().__init__(f"Chunk {chunk_id} does not belong to source {source_id}")


class LLMModelNotFound(ServiceError):
    status_code = 404

    def __init__(self, llm_model_id: UUID):
        self.llm_model_id = llm_model_id
        super().__init__(f"LLM model not found: {llm_model_id}")


class ComponentVersionCostNotFound(ServiceError):
    status_code = 404

    def __init__(self, component_version_id: UUID):
        self.component_version_id = component_version_id
        super().__init__(f"Component version cost not found: {component_version_id}")


class OrganizationLimitNotFound(ServiceError):
    status_code = 404

    def __init__(self, id: UUID, organization_id: UUID):
        self.id = id
        self.organization_id = organization_id
        super().__init__(f"Organization limit not found: {id} for organization {organization_id}")


class OrganizationLimitExceededError(ServiceError):
    """Raised when an organization has reached or exceeded its monthly credit limit."""
    status_code = 402

    def __init__(self, organization_id: UUID, limit: float, current_usage: float):
        self.organization_id = organization_id
        self.limit = limit
        self.current_usage = current_usage
        super().__init__(
            f"Organization has reached its monthly credit limit. "
            f"Limit: {limit} credits, Current usage: {current_usage} credits"
        )


class MissingDataSourceError(ServiceError):
    """Raised when a component requires a data source but none is configured."""
    status_code = 400

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


class GraphNotBoundToProjectError(ServiceError):
    """Raised when a graph is not bound to the expected project."""
    status_code = 403

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


class GraphVersionSavingFromNonDraftError(ServiceError):
    """Raised when attempting to save a version from a graph runner that is not in DRAFT environment."""
    status_code = 400

    def __init__(self, graph_runner_id: UUID, current_environment: str):
        self.graph_runner_id = graph_runner_id
        self.current_environment = current_environment
        super().__init__(
            f"Can only save versions from DRAFT. Graph runner {graph_runner_id} "
            f"is currently in environment: {current_environment}"
        )


class WidgetNotFound(ServiceError):
    status_code = 404

    def __init__(self, widget_id: UUID | None = None, widget_key: str | None = None):
        if widget_id:
            super().__init__(f"Widget with id {widget_id} not found")
        elif widget_key:
            super().__init__(f"Widget with key {widget_key} not found")
        else:
            super().__init__("Widget not found")


class WidgetDisabled(ServiceError):
    status_code = 403

    def __init__(self, widget_key: str):
        super().__init__(f"Widget {widget_key} is disabled")


class GraphRunnerAlreadyInEnvironmentError(ServiceError):
    status_code = 400

    def __init__(self, graph_runner_id: UUID, environment: str):
        self.graph_runner_id = graph_runner_id
        self.environment = environment
        super().__init__(f"Graph runner {graph_runner_id} is already in {environment}")


class MissingIntegrationError(ServiceError):
    """Raised when a component instance requires an integration but none is configured."""
    status_code = 400

    def __init__(self, integration_name: str, integration_service: str, component_instance_name: str):
        self.integration_name = integration_name
        self.integration_service = integration_service
        self.component_instance_name = component_instance_name
        super().__init__(
            f"Please add integration {integration_name}:{integration_service} "
            f"for component instance {component_instance_name}"
        )


class OAuthConnectionNotFoundError(ServiceError):
    """Raised when an OAuth connection is not found."""
    status_code = 404

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


class OAuthConnectionUnauthorizedError(ServiceError):
    """Raised when attempting to access an OAuth connection that doesn't belong to the organization."""
    status_code = 403

    def __init__(self, connection_id: UUID, organization_id: UUID):
        self.connection_id = connection_id
        self.organization_id = organization_id
        super().__init__(f"OAuth connection {connection_id} does not belong to organization {organization_id}")


class NangoConnectionNotFoundError(ServiceError):
    """Raised when a connection is not found in Nango (OAuth flow incomplete)."""
    status_code = 404

    def __init__(self, organization_id: UUID, provider: str):
        self.organization_id = organization_id
        self.provider = provider
        super().__init__(
            f"Connection not found in Nango for organization {organization_id}, provider {provider}. "
            "OAuth flow may not be complete."
        )


class NangoTokenMissingError(ServiceError):
    """Raised when access token is not found in Nango credentials."""
    status_code = 400

    def __init__(self, connection_id: UUID):
        self.connection_id = connection_id
        super().__init__(
            f"Access token not found in Nango credentials for connection {connection_id}",
        )


class VariableDefinitionNotFound(ServiceError):
    status_code = 404

    def __init__(self, name: str, organization_id: UUID):
        self.name = name
        self.organization_id = organization_id
        super().__init__(f"Variable definition '{name}' not found for organization {organization_id}")


class VariableSetNotFound(ServiceError):
    status_code = 404

    def __init__(self, set_id: str, organization_id: UUID):
        self.set_id = set_id
        self.organization_id = organization_id
        super().__init__(f"Variable set '{set_id}' not found for organization {organization_id}")


class OAuthSetProtectedError(ServiceError):
    status_code = 403

    def __init__(self, set_id: str):
        self.set_id = set_id
        super().__init__(f"OAuth set '{set_id}' is managed by OAuth and cannot be modified directly")


class RunError(ServiceError):
    """Raised when a graph execution fails, carrying the trace_id so callers can link the run to its trace."""
    status_code = 400

    def __init__(self, message: str, trace_id: str | None = None):
        self.trace_id = trace_id
        super().__init__(message)


class GraphConflictError(ServiceError):
    """Raised when a graph update conflicts with a more recent modification."""
    status_code = 409

    def __init__(self, graph_runner_id: UUID):
        self.graph_runner_id = graph_runner_id
        super().__init__(
            f"Graph {graph_runner_id} was modified by another client since you last fetched it. "
            "Refresh the graph and retry your changes."
        )


class DuplicateAlertEmailError(ServiceError):
    status_code = 409

    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Email {email} is already configured for this project")


class NotFoundError(ServiceError):
    status_code = 404

    def __init__(self, message: str):
        super().__init__(message)


class PromptNotFound(ServiceError):
    status_code = 404

    def __init__(self, prompt_id: UUID):
        self.prompt_id = prompt_id
        super().__init__(f"Prompt not found: {prompt_id}")


class PromptVersionNotFound(ServiceError):
    status_code = 404

    def __init__(self, version_id: UUID):
        self.version_id = version_id
        super().__init__(f"Prompt version not found: {version_id}")


class PromptStillPinnedError(ServiceError):
    status_code = 409

    def __init__(self, prompt_id: UUID):
        self.prompt_id = prompt_id
        super().__init__(f"Cannot delete prompt {prompt_id}: it is still pinned by one or more workflows")


class PromptNameConflictError(ServiceError):
    status_code = 409

    def __init__(self, name: str, organization_id: UUID):
        self.name = name
        self.organization_id = organization_id
        super().__init__(f"Prompt with name '{name}' already exists in organization {organization_id}")
