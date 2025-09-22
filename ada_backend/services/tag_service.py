from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.repositories.tag_repository import list_tag_versions


def list_tag_versions_service(session: Session, project_id: UUID) -> list[str]:
    return list_tag_versions(session, project_id)
