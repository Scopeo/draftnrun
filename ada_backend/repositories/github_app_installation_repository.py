from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def get_by_installation_id(session: Session, installation_id: int) -> db.GitHubAppInstallation | None:
    return (
        session.query(db.GitHubAppInstallation)
        .filter(db.GitHubAppInstallation.github_installation_id == installation_id)
        .first()
    )


def register_installation(session: Session, installation_id: int, organization_id: UUID) -> db.GitHubAppInstallation:
    row = db.GitHubAppInstallation(
        github_installation_id=installation_id,
        organization_id=organization_id,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
