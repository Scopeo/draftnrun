from datetime import datetime
from uuid import UUID
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def get_integration(
    session: Session,
    integration_id: UUID,
) -> db.Integration:
    return session.query(db.Integration).filter(db.Integration.id == integration_id).first()


def get_component_instance_integration_relationship(
    session: Session,
    component_instance_id: UUID,
) -> Optional[db.IntegrationComponentInstanceRelationship]:
    return (
        session.query(db.IntegrationComponentInstanceRelationship)
        .filter(
            db.IntegrationComponentInstanceRelationship.component_instance_id == component_instance_id,
        )
        .first()
    )


def upsert_secret_integration(
    session: Session,
    integration_id: UUID,
    access_token: str,
    refresh_token: str,
    expires_in: Optional[int] = None,
    token_last_updated: Optional[datetime] = None,
) -> db.SecretIntegration:
    """
    Upserts a secret integration into the database.
    If it exists and has the same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """
    existing_integration = (
        session.query(db.SecretIntegration)
        .filter(
            db.SecretIntegration.integration_id == integration_id,
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
    new_integration = db.SecretIntegration(
        integration_id=integration_id,
        expires_in=expires_in,
        token_last_updated=token_last_updated,
    )
    new_integration.set_access_token(access_token)
    new_integration.set_refresh_token(refresh_token)
    session.add(new_integration)
    session.commit()
    return new_integration


def upsert_component_instance_integration(
    session: Session,
    component_instance_id: UUID,
    secret_integration_id: UUID,
) -> db.IntegrationComponentInstanceRelationship:
    """
    Upserts a component instance integration relationship.
    If it exists, it will be updated; if not, it will be created.
    """
    existing_relationship = (
        session.query(db.IntegrationComponentInstanceRelationship)
        .filter(
            db.IntegrationComponentInstanceRelationship.component_instance_id == component_instance_id,
            db.IntegrationComponentInstanceRelationship.secret_integration_id == secret_integration_id,
        )
        .first()
    )

    if existing_relationship:
        return existing_relationship

    new_relationship = db.IntegrationComponentInstanceRelationship(
        component_instance_id=component_instance_id, secret_integration_id=secret_integration_id
    )
    session.add(new_relationship)
    session.commit()
    return new_relationship
