from sqlalchemy import UUID
from sqlalchemy.orm import Session

import ada_backend.database.models as db


def fetch_agents_with_graph_runners_by_organization(
    session: Session, organization_id: UUID
) -> list[tuple[db.AgentProject, db.GraphRunner, db.ProjectEnvironmentBinding]]:
    rows = (
        session.query(db.AgentProject, db.GraphRunner, db.ProjectEnvironmentBinding)
        .join(db.ProjectEnvironmentBinding, db.ProjectEnvironmentBinding.project_id == db.AgentProject.id)
        .join(db.GraphRunner, db.GraphRunner.id == db.ProjectEnvironmentBinding.graph_runner_id)
        .filter(db.AgentProject.organization_id == organization_id)
        .order_by(db.AgentProject.created_at, db.GraphRunner.created_at)
        .all()
    )
    return rows
