from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ada_backend.database import models as db


class ProjectIntegrationDTO(BaseModel):
    integration_id: UUID
    name: str
    service: str
    secret_id: UUID


def get_integration(
    session: Session,
    integration_id: UUID,
) -> db.Integration:
    return session.query(db.Integration).filter(db.Integration.id == integration_id).first()


def get_project_integration(
    session: Session,
    project_id: UUID,
    integration_id: UUID,
) -> Optional[ProjectIntegrationDTO]:
    print(f"Retrieving project integration for project_id: {project_id}, integration_id: {integration_id}")

    integration_project = (
        session.query(db.ProjectIntegration, db.Integration)
        .join(db.Integration, db.ProjectIntegration.integration_id == db.Integration.id)
        .filter(
            db.ProjectIntegration.project_id == project_id,
            db.ProjectIntegration.integration_id == integration_id,
        )
        .first()
    )
    if integration_project:
        return ProjectIntegrationDTO(
            secret_id=integration_project.id,
            integration_id=integration_project.integration_id,
            name=integration_project.name,
            service=integration_project.service,
        )
    return None


def get_integration_from_component(
    session: Session,
    component_id: UUID,
) -> Optional[db.ProjectIntegration]:

    return (
        session.query(db.ProjectIntegration)
        .join(db.Component, db.ProjectIntegration.integration_id == db.Component.integration_id)
        .filter(
            db.Component.id == component_id,
        )
        .first()
    )


def upsert_project_integration(
    session: Session,
    project_id: UUID,
    integration_id: UUID,
    access_token: str,
    refresh_token: str,
    expires_in: Optional[int] = None,
    token_last_updated: Optional[datetime] = None,
) -> db.ProjectIntegration:
    """
    Upserts a project integration into the database.
    If it exists and has the same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """
    existing_integration = (
        session.query(db.ProjectIntegration)
        .filter(
            db.ProjectIntegration.project_id == project_id,
            db.ProjectIntegration.integration_id == integration_id,
        )
        .first()
    )

    if existing_integration:
        existing_integration.expires_in = expires_in
        existing_integration.token_last_updated = token_last_updated
        existing_integration.set_access_token(access_token)
        existing_integration.set_refresh_token(refresh_token)
        session.commit()
        return existing_integration

    # Insert new integration
    new_integration = db.ProjectIntegration(
        project_id=project_id,
        integration_id=integration_id,
        expires_in=expires_in,
        token_last_updated=token_last_updated,
    )
    new_integration.set_access_token(access_token)
    new_integration.set_refresh_token(refresh_token)
    session.add(new_integration)
    session.commit()
    return new_integration
