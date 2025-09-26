import json
import uuid
from sqlalchemy import UUID
from sqlalchemy.orm import Session

import ada_backend.database.models as db
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.repositories.graph_runner_repository import upsert_component_node
from ada_backend.repositories.utils import create_component_instance


def get_agents_by_organization(session: Session, organization_id: UUID) -> list[db.AgentProject]:
    return session.query(db.AgentProject).filter(db.AgentProject.organization_id == organization_id).all()


def delete_agent(session, agent_id) -> bool:
    agent = session.query(db.AgentProject).filter(db.AgentProject.id == agent_id).first()
    if agent:
        session.delete(agent)
        session.commit()
        return True
    return False


def add_ai_agent_component_to_graph(session: Session, graph_runner_id: UUID) -> db.ComponentInstance:
    """
    Adds an AI agent component as a start node to the graph runner.

    Args:
        session (Session): SQLAlchemy session
        graph_runner_id (UUID): ID of the graph runner

    Returns:
        ComponentInstance: The created AI agent component instance
    """
    ai_agent_component = create_component_instance(
        session, component_id=COMPONENT_UUIDS["base_ai_agent"], name="AI Agent", component_instance_id=graph_runner_id
    )

    upsert_component_node(
        session=session,
        graph_runner_id=graph_runner_id,
        component_instance_id=ai_agent_component.id,
        is_start_node=True,
    )

    session.commit()
    return ai_agent_component
