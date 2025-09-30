from sqlalchemy import UUID
from sqlalchemy.orm import Session

import ada_backend.database.models as db


def fetch_agents_with_graph_runners_by_organization(
    session: Session, organization_id: UUID
) -> tuple[db.AgentProject, db.ProjectEnvironmentBinding]:
    rows = (
        session.query(db.AgentProject, db.ProjectEnvironmentBinding)
        .join(db.ProjectEnvironmentBinding, db.ProjectEnvironmentBinding.project_id == db.AgentProject.id)
        .filter(db.AgentProject.organization_id == organization_id)
        .all()
    )
    return rows
