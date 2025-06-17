from uuid import UUID
import logging

from sqlalchemy.orm import Session

from ada_backend.repositories.component_repository import delete_component_instances
from ada_backend.repositories.graph_runner_repository import delete_graph_runner, get_component_nodes

LOGGER = logging.getLogger(__name__)


def delete_component_instances_from_nodes(session: Session, component_node_ids: set[UUID]) -> None:
    """
    Deletes component instances from the database.

    Args:
        session (Session): SQLAlchemy session.
        graph_nodes (list[ComponentNodeDTO]): List of component nodes to delete.
    """
    delete_component_instances(session, component_instance_ids=component_node_ids)
    LOGGER.info("Deleted instances: {}".format(len(component_node_ids)))


def delete_graph_runner_service(session: Session, graph_runner_id: UUID):
    """
    Deletes a graph runner and all its associated nodes and edges.

    Args:
        session (Session): SQLAlchemy session.
        graph_runner_id (UUID): ID of the graph runner to delete.
    """
    graph_nodes = get_component_nodes(session, graph_runner_id)
    delete_graph_runner(session, graph_runner_id)

    # Delete all component instances associated with the graph runner
    delete_component_instances_from_nodes(session, component_node_ids={node.id for node in graph_nodes})
