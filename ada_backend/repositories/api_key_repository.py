from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ada_backend.database import models as db


async def create_api_key(
    session: AsyncSession,
    project_id: UUID,
    key_name: str,
    hashed_key: str,
    creator_user_id: UUID,
) -> UUID:
    """Creates a new API key for the given user, returns the key id."""
    new_api_key = db.ApiKey(
        project_id=project_id,
        public_key=hashed_key,
        name=key_name,
        creator_user_id=creator_user_id,
    )
    session.add(new_api_key)
    await session.commit()
    await session.refresh(new_api_key)
    return new_api_key.id


async def get_api_key_by_hashed_key(session: AsyncSession, hashed_key: str) -> Optional[db.ApiKey]:
    """Retrieves an API key by its public key."""
    result = await session.execute(
        select(db.ApiKey).filter(db.ApiKey.public_key == hashed_key)
    )
    return result.scalar_one_or_none()


async def get_api_keys_by_project_id(session: AsyncSession, project_id: UUID) -> list[db.ApiKey]:
    """Retrieves all active API keys by project id."""
    result = await session.execute(
        select(db.ApiKey).filter(
            db.ApiKey.project_id == project_id,
            db.ApiKey.is_active.is_(True),
        )
    )
    return result.scalars().all()


async def deactivate_api_key(session: AsyncSession, key_id: UUID, revoker_user_id: UUID) -> UUID:
    """Deactivates an API key by setting is_active to False, returns the key id."""
    result = await session.execute(
        select(db.ApiKey).filter(db.ApiKey.id == key_id)
    )
    api_key_entry = result.scalar_one_or_none()
    if api_key_entry:
        api_key_entry.is_active = False
        api_key_entry.revoker_user_id = revoker_user_id
        await session.commit()
    return key_id


async def get_project_by_api_key(
    session: AsyncSession,
    hashed_key: str,
) -> Optional[db.Project]:
    """Retrieves the project associated with an API key."""
    result = await session.execute(
        select(db.Project)
        .join(db.ApiKey, db.ApiKey.project_id == db.Project.id)
        .filter(db.ApiKey.public_key == hashed_key)
    )
    return result.scalar_one_or_none()
