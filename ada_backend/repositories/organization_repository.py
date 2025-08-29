from typing import Optional
from uuid import UUID
import logging
from dataclasses import dataclass

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

    Returns:
        db.OrganizationSecret: The newly created OrganizationSecret object.
    """
    organization_secret = (
        session.query(db.OrganizationSecret)
        .filter(
            db.OrganizationSecret.organization_id == organization_id,
            db.OrganizationSecret.key == key,
            db.OrganizationSecret.secret_type == secret_type,
        )
        .first()
    )
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
