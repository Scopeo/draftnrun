from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def create_api_key(
    session: Session,
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
    session.commit()
    return new_api_key.id


def get_api_key_by_hashed_key(session: Session, hashed_key: str) -> Optional[db.ApiKey]:
    """Retrieves an API key by its public key."""
    return (
        session.query(db.ApiKey)
        .filter(
            db.ApiKey.public_key == hashed_key,
        )
        .first()
    )


def get_api_keys_by_project_id(session: Session, project_id: UUID) -> list[db.ApiKey]:
    """Retrieves all active API keys by project id."""
    return (
        session.query(db.ApiKey)
        .filter(
            db.ApiKey.project_id == project_id,
            db.ApiKey.is_active.is_(True),
        )
        .all()
    )


def deactivate_api_key(session: Session, key_id: UUID, revoker_user_id: UUID) -> UUID:
    """Deactivates an API key by setting is_active to False, returns the key id."""
    api_key_entry = session.query(db.ApiKey).filter(db.ApiKey.id == key_id).first()
    if api_key_entry:
        api_key_entry.is_active = False
        api_key_entry.revoker_user_id = revoker_user_id
        session.commit()
    return key_id


def get_project_by_api_key(
    session: Session,
    hashed_key: str,
) -> Optional[db.Project]:
    """
    Retrieves the project associated with an API key.
    """
    return (
        session.query(db.Project)
        .join(
            db.ApiKey,
            db.ApiKey.project_id == db.Project.id,
        )
        .filter(db.ApiKey.public_key == hashed_key)
        .first()
    )
