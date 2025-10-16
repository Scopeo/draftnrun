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


class ProtectedComponentDeletionError(Exception):
    def __init__(self, component_id):
        self.component_id = component_id
        super().__init__(f"Deletion forbidden: component {component_id} is protected and cannot be deleted")


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
