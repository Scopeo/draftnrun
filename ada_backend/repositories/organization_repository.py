import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


# --- DTOs ---
@dataclass
class OrganizationSecretDTO:
    id: UUID
    organization_id: UUID
    key: str
    secret: str
    secret_type: db.OrgSecretType


def get_organization_secrets(
    session: Session,
    organization_id: UUID,
    key: Optional[str] = None,
) -> list[OrganizationSecretDTO]:
    """
    Retrieves organization secrets. If a key is provided, fetches the specific secret.
    Otherwise, fetches all secrets for the organization.

    Args:
        session (Session): SQLAlchemy session object.
        organization_id (UUID): ID of the organization.
        key (Optional[str]): Optional key to filter the secrets.

    Returns:
        list[OrganizationSecretDTO]: List of OrganizationSecretDTO objects.
    """
    query = session.query(db.OrganizationSecret).filter(
        db.OrganizationSecret.organization_id == organization_id,
    )
    if key:
        query = query.filter(db.OrganizationSecret.key == key)
    project_secrets = query.all()
    return [
        OrganizationSecretDTO(
            id=secret.id,
            organization_id=organization_id,
            key=secret.key,
            secret=secret.get_secret(),
            secret_type=secret.secret_type,
        )
        for secret in project_secrets
    ]


def get_organization_secrets_from_project_id(
    sessin: Session,
    project_id: UUID,
    key: Optional[str] = None,
) -> list[OrganizationSecretDTO]:
    organization_id = sessin.query(db.Project.organization_id).filter(db.Project.id == project_id).scalar()
    if not organization_id:
        raise ValueError(f"Project with ID {project_id} does not exist.")

    return get_organization_secrets(sessin, organization_id, key=key)


def upsert_organization_secret(
    session: Session,
    organization_id: UUID,
    key: str,
    secret: str,
    secret_type: Optional[db.OrgSecretType] = None,
) -> db.OrganizationSecret:
    """
    Inserts a new organization secret into the database.

    Args:
        session (Session): SQLAlchemy session.
        organization_id (UUID): ID of the organization.
        key (str): Key for the secret.
        secret (str): Secret value to be encrypted and stored.
        secret_type (Optional[db.OrgSecretType]): Type of secret. If None, uses database default.

    Returns:
        db.OrganizationSecret: The newly created OrganizationSecret object.
    """
    # Build query - only filter by secret_type if explicitly provided
    query = session.query(db.OrganizationSecret).filter(
        db.OrganizationSecret.organization_id == organization_id,
        db.OrganizationSecret.key == key,
    )

    # Only filter by secret_type if it's explicitly provided to avoid mismatch with DB defaults
    if secret_type is not None:
        query = query.filter(db.OrganizationSecret.secret_type == secret_type)

    organization_secret = query.first()

    if not organization_secret:
        LOGGER.info(f"Creating new secret with key {key} for organization {organization_id}")
        organization_secret = db.OrganizationSecret(organization_id=organization_id, key=key, secret_type=secret_type)
    else:
        LOGGER.info(f"Updating existing secret with key {key} for organization {organization_id}")
    organization_secret.set_secret(secret)
    session.add(organization_secret)
    session.commit()
    session.refresh(organization_secret)
    return organization_secret


def get_variable_secret(
    session: Session,
    variable_definition_id: UUID,
    variable_set_id: Optional[UUID] = None,
) -> Optional[db.OrganizationSecret]:
    return (
        session.query(db.OrganizationSecret)
        .filter(
            db.OrganizationSecret.variable_definition_id == variable_definition_id,
            db.OrganizationSecret.variable_set_id == variable_set_id,
        )
        .first()
    )


def upsert_variable_secret(
    session: Session,
    organization_id: UUID,
    definition_id: UUID,
    variable_set_id: Optional[UUID],
    key: str,
    secret: str,
) -> db.OrganizationSecret:
    row = get_variable_secret(session, definition_id, variable_set_id)
    if not row:
        row = db.OrganizationSecret(
            organization_id=organization_id,
            key=key,
            secret_type=db.OrgSecretType.VARIABLE,
            variable_definition_id=definition_id,
            variable_set_id=variable_set_id,
        )
    row.set_secret(secret)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_variable_secrets_for_set(
    session: Session,
    variable_set_id: UUID,
) -> list[db.OrganizationSecret]:
    return (
        session.query(db.OrganizationSecret)
        .filter(
            db.OrganizationSecret.variable_set_id == variable_set_id,
            db.OrganizationSecret.secret_type == db.OrgSecretType.VARIABLE,
        )
        .all()
    )


def list_variable_secrets_for_definitions(
    session: Session,
    definition_ids: list[UUID],
    variable_set_id: Optional[UUID] = None,
) -> list[db.OrganizationSecret]:
    return (
        session.query(db.OrganizationSecret)
        .filter(
            db.OrganizationSecret.variable_definition_id.in_(definition_ids),
            db.OrganizationSecret.variable_set_id == variable_set_id,
            db.OrganizationSecret.secret_type == db.OrgSecretType.VARIABLE,
        )
        .all()
    )


def delete_organization_secret(
    session: Session,
    organization_id: UUID,
    key: str,
) -> db.OrganizationSecret:
    organization_secret = (
        session.query(db.OrganizationSecret)
        .filter(
            db.OrganizationSecret.organization_id == organization_id,
            db.OrganizationSecret.key == key,
        )
        .first()
    )
    if not organization_secret:
        raise ValueError(f"Secret with key {key} not found for organization {organization_id}")
    if organization_secret:
        LOGGER.info(f"Deleting secret with key {key} for organization {organization_id}")
        session.delete(organization_secret)
        session.commit()
    return organization_secret
