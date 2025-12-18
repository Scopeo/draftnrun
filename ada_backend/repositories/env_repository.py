from uuid import UUID
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import EnvType


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
    env: EnvType = None,
) -> db.ProjectEnvironmentBinding:
    # Case env is None -> we create a new version, so we need to create the relationship
    if env is None:
        relationship = db.ProjectEnvironmentBinding(
            graph_runner_id=graph_runner_id, project_id=project_id, environment=None
        )
        session.add(relationship)
        session.commit()
        return relationship
    # We do not create a version but a draft/production one, so we check that we have a single relationship per env
    # and update it if it exists
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
