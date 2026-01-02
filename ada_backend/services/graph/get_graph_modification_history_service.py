import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.graph_runner_repository import get_modification_history
from ada_backend.schemas.pipeline.graph_schema import (
    GraphModificationHistoryResponse,
    ModificationHistoryItem,
)
from ada_backend.services.graph.graph_validation_utils import validate_graph_runner_belongs_to_project

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
    validate_graph_runner_belongs_to_project(session, graph_runner_id, project_id)

    history_records = get_modification_history(session, graph_runner_id)

    history_items = [
        ModificationHistoryItem(
            time=record.created_at,
            user_id=record.user_id,
        )
        for record in history_records
    ]

    return GraphModificationHistoryResponse(history=history_items)
