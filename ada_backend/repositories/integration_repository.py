from datetime import datetime
from uuid import UUID
from typing import Optional
import logging

from sqlalchemy.orm import Session

from ada_backend.database import models as db


LOGGER = logging.getLogger(__name__)


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


def get_integration_secret(
    session: Session,
    integration_secret_id: UUID,
) -> Optional[db.SecretIntegration]:
    return session.query(db.SecretIntegration).filter(db.SecretIntegration.id == integration_secret_id).first()


def get_integration_from_component(
    session: Session,
    component_id: UUID,
) -> db.Integration:
    return (
        session.query(db.Integration)
        .join(db.Component, db.Integration.id == db.Component.integration_id)
        .filter(
            db.Component.id == component_id,
            db.Component.integration_id.isnot(None),
        )
        .first()
    )


def insert_secret_integration(
    session: Session,
    integration_id: UUID,
    access_token: str,
    refresh_token: str,
    expires_in: Optional[int] = None,
    token_last_updated: Optional[datetime] = None,
) -> db.SecretIntegration:

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


def update_integration_secret(
    session: Session,
    integration_secret_id: UUID,
    access_token: str,
    refresh_token: str,
    token_last_updated: datetime,
) -> None:
    integration_secret = get_integration_secret(session, integration_secret_id)
    if integration_secret:
        integration_secret.set_access_token(access_token)
        integration_secret.set_refresh_token(refresh_token)
        integration_secret.token_last_updated = token_last_updated
        session.commit()


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


def delete_linked_integration(
    session: Session,
    component_instance_id: UUID,
) -> None:
    """
    Deletes the linked integration for a component instance.
    If the integration is not used by any other component instance, it will also delete the secret integration.
    """
    relationship = get_component_instance_integration_relationship(session, component_instance_id)
    if relationship:
        secret_integration_id = relationship.secret_integration_id
        session.delete(relationship)
        session.commit()
        if (
            session.query(db.IntegrationComponentInstanceRelationship)
            .filter(db.IntegrationComponentInstanceRelationship.id == secret_integration_id)
            .count()
        ) == 0:
            secret_integration = (
                session.query(db.SecretIntegration).filter(db.SecretIntegration.id == secret_integration_id).first()
            )
            if secret_integration:
                LOGGER.info(
                    f"Deleting secret integration {secret_integration_id} as it is no longer "
                    "linked to any component instance."
                )
                session.delete(secret_integration)
                session.commit()
