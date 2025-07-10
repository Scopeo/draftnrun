from typing import Optional
from uuid import UUID
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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


async def get_organization_secrets(
    session: AsyncSession,
    organization_id: UUID,
    key: Optional[str] = None,
) -> list[OrganizationSecretDTO]:
    """
    Retrieves organization secrets asynchronously. If a key is provided, fetches the specific secret.
    Otherwise, fetches all secrets for the organization.

    Args:
        session (AsyncSession): SQLAlchemy asynchronous session object.
        organization_id (UUID): ID of the organization.
        key (Optional[str]): Optional key to filter the secrets.

    Returns:
        list[OrganizationSecretDTO]: List of OrganizationSecretDTO objects.
    """
    stmt = select(db.OrganizationSecret).where(
        db.OrganizationSecret.organization_id == organization_id,
    )
    if key:
        stmt = stmt.where(db.OrganizationSecret.key == key)
    result = await session.execute(stmt)
    project_secrets = result.scalars().all()
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


async def get_organization_secrets_from_project_id(
    session: AsyncSession,
    project_id: UUID,
    key: Optional[str] = None,
) -> list[OrganizationSecretDTO]:
    """
    Retrieves organization secrets based on a project ID asynchronously.
    """
    stmt = select(db.Project.organization_id).where(db.Project.id == project_id)
    organization_id = (await session.execute(stmt)).scalar_one_or_none()
    if not organization_id:
        raise ValueError(f"Project with ID {project_id} does not exist.")

    return await get_organization_secrets(session, organization_id, key=key)


async def upsert_organization_secret(
    session: AsyncSession,
    organization_id: UUID,
    key: str,
    secret: str,
) -> db.OrganizationSecret:
    """
    Inserts a new organization secret or updates an existing one into the database asynchronously.

    Args:
        session (AsyncSession): SQLAlchemy asynchronous session.
        organization_id (UUID): ID of the organization.
        key (str): Key for the secret.
        secret (str): Secret value to be encrypted and stored.

    Returns:
        db.OrganizationSecret: The newly created or updated OrganizationSecret object.
    """
    stmt = select(db.OrganizationSecret).where(
        db.OrganizationSecret.organization_id == organization_id,
        db.OrganizationSecret.key == key,
    )
    organization_secret = (await session.execute(stmt)).scalar_one_or_none()

    if not organization_secret:
        LOGGER.info(f"Creating new secret with key {key} for organization {organization_id}")
        organization_secret = db.OrganizationSecret(organization_id=organization_id, key=key)
    else:
        LOGGER.info(f"Updating existing secret with key {key} for organization {organization_id}")
    organization_secret.set_secret(secret)
    session.add(organization_secret)
    await session.commit()
    await session.refresh(organization_secret)
    return organization_secret


async def delete_organization_secret(
    session: AsyncSession,
    organization_id: UUID,
    key: str,
) -> db.OrganizationSecret:
    """
    Deletes an organization secret asynchronously.
    """
    stmt = select(db.OrganizationSecret).where(
        db.OrganizationSecret.organization_id == organization_id,
        db.OrganizationSecret.key == key,
    )
    organization_secret = (await session.execute(stmt)).scalar_one_or_none()

    if not organization_secret:
        raise ValueError(f"Secret with key {key} not found for organization {organization_id}")

    LOGGER.info(f"Deleting secret with key {key} for organization {organization_id}")
    await session.delete(organization_secret)
    await session.commit()
    return organization_secret
