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


class ComponentHasInstancesDeletionError(Exception):
    def __init__(self, component_id, instance_count):
        self.component_id = component_id
        super().__init__(
            f"Deletion forbidden: component {component_id} currently has {instance_count} active instances in projects"
        )


class ComponentVersionInUseError(Exception):
    def __init__(self, component_version_id: UUID, instance_count: int):
        self.component_version_id = component_version_id
        self.instance_count = instance_count
        super().__init__(
            f"Cannot delete component version {component_version_id}: "
            f"it is currently used by {instance_count} instance(s)"
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
