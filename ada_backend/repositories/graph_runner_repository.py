from typing import Optional
from uuid import UUID
import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import select, exists

from ada_backend.database import models as db
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.schemas.pipeline.graph_schema import ComponentNodeDTO
from ada_backend.repositories.utils import create_input_component


LOGGER = logging.getLogger(__name__)


def get_graph_runners_by_project(session: Session, project_id: UUID) -> list[db.GraphRunner]:
    return (
        session.query(db.GraphRunner)
        .join(
            db.ProjectEnvironmentBinding,
            db.GraphRunner.id == db.ProjectEnvironmentBinding.graph_runner_id,
        )
        .filter(db.ProjectEnvironmentBinding.project_id == project_id)
        .all()
    )


def get_graph_runner_for_env(
    session: Session,
    project_id: UUID,
    env: db.EnvType,
) -> Optional[db.GraphRunner]:
    """Returns the GraphRunner bound to the given project and environment."""
    return (
        session.query(db.GraphRunner)
        .join(
            db.ProjectEnvironmentBinding,
            db.GraphRunner.id == db.ProjectEnvironmentBinding.graph_runner_id,
        )
        .filter(
            db.ProjectEnvironmentBinding.project_id == project_id,
            db.ProjectEnvironmentBinding.environment == env,
        )
        .first()
    )


def get_graph_runner_for_tag_version(
    session: Session,
    project_id: UUID,
    tag_version: str,
) -> Optional[db.GraphRunner]:
    """Returns the GraphRunner bound to the given project and environment."""
    return (
        session.query(db.GraphRunner)
        .join(
            db.ProjectEnvironmentBinding,
            db.GraphRunner.id == db.ProjectEnvironmentBinding.graph_runner_id,
        )
        .filter(
            db.ProjectEnvironmentBinding.project_id == project_id,
            db.GraphRunner.tag_version == tag_version,
        )
        .first()
    )


def insert_graph_runner(
    session: Session,
    graph_id: UUID,
    add_input: bool = False,
) -> db.GraphRunner:
    """
    Inserts a new GraphRunner into the database.

    Returns:
        db.GraphRunner: The newly created GraphRunner object.
    """
    graph_runner = db.GraphRunner(id=graph_id)
    session.add(graph_runner)
    if add_input:
        add_input_component_to_graph(session, graph_id)
    session.commit()
    return graph_runner


def insert_graph_runner_and_bind_to_project(
    session: Session,
    graph_id: UUID,
    project_id: UUID,
    env: Optional[db.EnvType] = None,
) -> None:
    graph_runner = db.GraphRunner(id=graph_id)
    session.add(graph_runner)
    graph_runner_relationship = db.ProjectEnvironmentBinding(
        project_id=project_id, graph_runner_id=graph_id, environment=env
    )
    session.add(graph_runner_relationship)
    session.commit()


def upsert_component_node(
    session: Session, graph_runner_id: UUID, component_instance_id: UUID, is_start_node: bool = False
) -> None:
    node_to_graph_runner = (
        session.query(db.GraphRunnerNode)
        .filter(
            db.GraphRunnerNode.graph_runner_id == graph_runner_id,
            db.GraphRunnerNode.node_id == component_instance_id,
        )
        .first()
    )
    if node_to_graph_runner:
        # Update existing node
        node_to_graph_runner.is_start_node = is_start_node
    else:
        node_to_graph_runner = db.GraphRunnerNode(
            node_id=component_instance_id,
            graph_runner_id=graph_runner_id,
            node_type=db.NodeType.COMPONENT,
            is_start_node=is_start_node,
        )
        session.add(node_to_graph_runner)
    session.commit()


def graph_runner_exists(session: Session, graph_id: UUID) -> bool:
    """Check if a GraphRunner with the given ID exists."""
    stmt = select(exists().where((db.GraphRunner.id == graph_id)))
    return session.execute(stmt).scalar()


def get_component_nodes(session: Session, graph_runner_id: UUID) -> list[ComponentNodeDTO]:
    """
    Retrieves the component nodes associated with a graph.

    Args:
        session (Session): SQLAlchemy session.
        graph_runner_id (UUID): ID of the graph whose nodes to retrieve.

    Returns:
        list[ComponentNodeDTO]
    """
    results = (
        session.query(db.ComponentInstance, db.GraphRunnerNode)
        .join(
            db.GraphRunnerNode,
            db.ComponentInstance.id == db.GraphRunnerNode.node_id,
        )
        .filter(db.GraphRunnerNode.graph_runner_id == graph_runner_id)
        .all()
    )
    return [
        ComponentNodeDTO(
            id=component_instance.id,
            name=component_instance.name,
            is_start_node=node_to_graph_runner.is_start_node,
            component_instance_id=component_instance.id,
            graph_runner_id=graph_runner_id,
        )
        for component_instance, node_to_graph_runner in results
    ]


def get_graph_runner_nodes(session: Session, graph_runner_id: UUID) -> list[db.GraphRunner]:
    """
    Retrieves the graph runner nodes associated with a graph.

    Args:
        session (Session): SQLAlchemy session.
        graph_runner_id (UUID): ID of the graph runner whose nodes to retrieve.

    Returns:
        list[db.GraphRunner]: List of GraphRunner objects.
    """
    return (
        session.query(db.GraphRunner)
        .join(
            db.GraphRunnerNode,
            db.GraphRunner.id == db.GraphRunnerNode.node_id,
        )
        .filter(db.GraphRunnerNode.graph_runner_id == graph_runner_id)
        .all()
    )


def get_start_components(session: Session, graph_runner_id: UUID) -> list[db.ComponentInstance]:
    """
    Retirve start nodes of a graph.
    source_node_id is None
    """
    return (
        session.query(db.ComponentInstance)
        .join(db.GraphRunnerNode, db.GraphRunnerNode.node_id == db.ComponentInstance.id)
        .filter(db.GraphRunnerNode.graph_runner_id == graph_runner_id, db.GraphRunnerNode.is_start_node.is_(True))
        .all()
    )


def get_input_component(session: Session, graph_runner_id: UUID) -> db.ComponentInstance:
    """
    Retrieve input nodes of a graph.
    source_node_id is None
    """
    return (
        session.query(db.ComponentInstance)
        .join(db.GraphRunnerNode, db.GraphRunnerNode.node_id == db.ComponentInstance.id)
        .join(db.Component, db.Component.id == db.ComponentInstance.component_id)
        .filter(
            db.GraphRunnerNode.graph_runner_id == graph_runner_id,
            db.Component.id == COMPONENT_UUIDS["input"],
            db.GraphRunnerNode.is_start_node.is_(True),
        )
        .first()
    )


def delete_node(session: Session, node_id: UUID):
    """
    Deletes a node from the graph runner.

    Args:
        session (Session): SQLAlchemy session.
        node_id (UUID): ID of the node to delete.
    """
    node_to_graph_runner = session.query(db.GraphRunnerNode).filter(db.GraphRunnerNode.node_id == node_id).first()
    if node_to_graph_runner:
        LOGGER.info(f"Deleting node with id {node_id}")
        session.delete(node_to_graph_runner)
        session.commit()
    else:
        raise ValueError(f"Node with ID {node_id} does not exist in the graph runner.")


def delete_graph_runner(session: Session, graph_id: UUID) -> None:
    """Delete a GraphRunner with the given ID."""
    LOGGER.info(f"Deleting graph runner with id {graph_id}")
    session.query(db.GraphRunner).filter(db.GraphRunner.id == graph_id).delete()
    session.commit()


def add_input_component_to_graph(session: Session, graph_runner_id: UUID) -> db.ComponentInstance:
    """
    Adds an input component as a start node to the graph runner.

    Args:
        session (Session): SQLAlchemy session
        graph_runner_id (UUID): ID of the graph runner

    Returns:
        ComponentInstance: The created input component instance
    """
    # Create input component instance
    input_component = create_input_component(session)

    # Add it as a start node to the graph
    upsert_component_node(
        session=session, graph_runner_id=graph_runner_id, component_instance_id=input_component.id, is_start_node=True
    )

    session.commit()
    return input_component


def delete_temp_folder(uuid_for_temp_folder: str) -> None:
    temp_folder = Path(uuid_for_temp_folder)
    if temp_folder.exists():
        shutil.rmtree(temp_folder)
        LOGGER.info(f"Deleted temp folder: {temp_folder}")
