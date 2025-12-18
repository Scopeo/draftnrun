from uuid import UUID
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import EnvType
from ada_backend.database import models as db


def get_project_env_binding(
    session: Session, project_id: UUID, graph_runner_id: UUID
) -> db.ProjectEnvironmentBinding | None:
    return (
        session.query(db.ProjectEnvironmentBinding)
        .filter(
            db.ProjectEnvironmentBinding.graph_runner_id == graph_runner_id,
            db.ProjectEnvironmentBinding.project_id == project_id,
        )
        .first()
    )


def get_project_env_binding_by_env(
    session: Session, project_id: UUID, env: EnvType
) -> db.ProjectEnvironmentBinding | None:
    return (
        session.query(db.ProjectEnvironmentBinding)
        .filter(
            db.ProjectEnvironmentBinding.project_id == project_id,
            db.ProjectEnvironmentBinding.environment == env,
        )
        .first()
    )


def get_env_relationship_by_graph_runner_id(
    session: Session, graph_runner_id: UUID
) -> Optional[db.ProjectEnvironmentBinding]:
    return (
        session.query(db.ProjectEnvironmentBinding)
        .filter(db.ProjectEnvironmentBinding.graph_runner_id == graph_runner_id)
        .first()
    )


def update_graph_runner_env(session: Session, graph_runner_id: UUID, env: EnvType):
    env_relationship = (
        session.query(db.ProjectEnvironmentBinding)
        .filter(db.ProjectEnvironmentBinding.graph_runner_id == graph_runner_id)
        .first()
    )
    if not env_relationship:
        raise ValueError(f"Graph runner with ID {graph_runner_id} not found.")
    env_relationship.environment = env
    session.add(env_relationship)
    session.commit()


def bind_graph_runner_to_project(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    env: EnvType,
) -> db.ProjectEnvironmentBinding:
    existing_binding = (
        session.query(db.ProjectEnvironmentBinding)
        .filter(
            db.ProjectEnvironmentBinding.project_id == project_id,
            db.ProjectEnvironmentBinding.environment == env,
        )
        .first()
    )

    if existing_binding:
        existing_binding.graph_runner_id = graph_runner_id
        session.commit()
        return existing_binding

    relationship = db.ProjectEnvironmentBinding(
        graph_runner_id=graph_runner_id, project_id=project_id, environment=env
    )
    session.add(relationship)
    session.commit()
    return relationship
