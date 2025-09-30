from sqlalchemy import UUID
from sqlalchemy.orm import Session

import ada_backend.database.models as db


def get_agents_by_organization(session: Session, organization_id: UUID) -> list[db.AgentProject]:
    return session.query(db.AgentProject).filter(db.AgentProject.organization_id == organization_id).all()
