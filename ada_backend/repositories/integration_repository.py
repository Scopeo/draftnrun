from uuid import UUID
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def get_integration(
    session: Session,
    integration_id: UUID,
) -> db.Integration:
    return session.query(db.Integration).filter(db.Integration.id == integration_id).first()


def get_component_instance_integration(
    session: Session,
    component_instance_id: UUID,
    integration_id: UUID,
) -> Optional[db.ComponentIntegration]:
    return (
        session.query(db.ComponentIntegration)
        .filter(
            db.ComponentIntegration.component_instance_id == component_instance_id,
            db.ComponentIntegration.integration_id == integration_id,
        )
        .first()
    )


def upsert_component_integration(
    session: Session,
    component_instance_id: UUID,
    integration_id: UUID,
    access_token: str,
    refresh_token: str,
    expires_at: Optional[str] = None,
) -> db.ComponentIntegration:
    """
    Upserts a component integration into the database.
    If it exists and has the same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """
    existing_integration = (
        session.query(db.ComponentIntegration)
        .filter(
            db.ComponentIntegration.component_instance_id == component_instance_id,
            db.ComponentIntegration.integration_id == integration_id,
        )
        .first()
    )

    if existing_integration:
        existing_integration.expires_at = expires_at
        existing_integration.set_access_token(access_token)
        existing_integration.set_refresh_token(refresh_token)
        session.commit()
        return existing_integration

    # Insert new integration
    new_integration = db.ComponentIntegration(
        component_instance_id=component_instance_id,
        integration_id=integration_id,
        expires_at=expires_at,
    )
    new_integration.set_access_token(access_token)
    new_integration.set_refresh_token(refresh_token)
    session.add(new_integration)
    session.commit()
    return new_integration
