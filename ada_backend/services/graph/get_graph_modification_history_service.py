from uuid import UUID
import logging

from sqlalchemy.orm import Session

from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.repositories.graph_runner_repository import (
    graph_runner_exists,
    get_modification_history,
)
from ada_backend.schemas.pipeline.graph_schema import (
    GraphModificationHistoryResponse,
    ModificationHistoryItem,
)
from ada_backend.services.errors import GraphNotFound

LOGGER = logging.getLogger(__name__)


def get_graph_modification_history_service(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
) -> GraphModificationHistoryResponse:
    """
    Get the modification history for a graph runner.

    Args:
        session: Database session
        project_id: Project ID
        graph_runner_id: Graph runner ID

    Returns:
        GraphModificationHistoryResponse: List of modification history entries

    Raises:
        GraphNotFound: If the graph runner doesn't exist
        ValueError: If the graph runner is not bound to the project
    """
    if not graph_runner_exists(session, graph_runner_id):
        raise GraphNotFound(graph_runner_id)

    project_env_binding = get_env_relationship_by_graph_runner_id(session, graph_runner_id)
    if not project_env_binding:
        raise ValueError(f"Graph with ID {graph_runner_id} is not bound to any project.")
    if project_env_binding.project_id != project_id:
        raise ValueError(
            f"Graph with ID {graph_runner_id} is bound to project {project_env_binding.project_id}, not {project_id}."
        )

    history_records = get_modification_history(session, graph_runner_id)

    history_items = [
        ModificationHistoryItem(
            time=record.created_at,
            user_id=record.user_id,
        )
        for record in history_records
    ]

    return GraphModificationHistoryResponse(history=history_items)
