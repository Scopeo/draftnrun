from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.repositories.graph_runner_repository import graph_runner_exists
from ada_backend.services.errors import GraphNotFound, GraphNotBoundToProjectError


def validate_graph_runner_belongs_to_project(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
) -> db.ProjectEnvironmentBinding:
    if not graph_runner_exists(session, graph_runner_id):
        raise GraphNotFound(graph_runner_id)

    project_env_binding = get_env_relationship_by_graph_runner_id(session, graph_runner_id)
    if not project_env_binding:
        raise GraphNotBoundToProjectError(graph_runner_id)
    if project_env_binding.project_id != project_id:
        raise GraphNotBoundToProjectError(graph_runner_id, project_env_binding.project_id, project_id)

    return project_env_binding
