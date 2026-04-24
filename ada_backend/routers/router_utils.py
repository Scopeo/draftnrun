from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import Project
from ada_backend.services.errors import ProjectNotFound


def resolve_organization_id(session: Session, project_id: UUID) -> UUID:
    """Look up the organization_id that owns the given project."""
    org_id = session.query(Project.organization_id).filter(Project.id == project_id).scalar()
    if org_id is None:
        raise ProjectNotFound(f"Project {project_id} not found")
    return org_id
