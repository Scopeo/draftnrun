"""
Repository for OAuth connections managed by Nango.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def create_oauth_connection(
    session: Session,
    connection_id: UUID,
    organization_id: UUID,
    provider_config_key: str,
    nango_connection_id: str,
    name: str = "",
    created_by_user_id: UUID | None = None,
) -> db.OAuthConnection:
    connection = db.OAuthConnection(
        id=connection_id,
        organization_id=organization_id,
        provider_config_key=provider_config_key,
        nango_connection_id=nango_connection_id,
        name=name,
        created_by_user_id=created_by_user_id,
    )
    session.add(connection)
    session.commit()
    session.refresh(connection)

    return connection


def get_oauth_connection_by_id(
    session: Session,
    connection_id: UUID,
) -> db.OAuthConnection | None:
    return (
        session.query(db.OAuthConnection)
        .filter(db.OAuthConnection.id == connection_id, db.OAuthConnection.deleted_at.is_(None))
        .first()
    )


def get_oauth_connection_by_nango_id(
    session: Session,
    nango_connection_id: str,
) -> db.OAuthConnection | None:
    return (
        session.query(db.OAuthConnection)
        .filter(db.OAuthConnection.nango_connection_id == nango_connection_id, db.OAuthConnection.deleted_at.is_(None))
        .first()
    )


def list_oauth_connections_by_organization(
    session: Session,
    organization_id: UUID,
    provider_config_key: str | None = None,
) -> list[db.OAuthConnection]:
    query = session.query(db.OAuthConnection).filter(
        db.OAuthConnection.organization_id == organization_id, db.OAuthConnection.deleted_at.is_(None)
    )

    if provider_config_key:
        query = query.filter(db.OAuthConnection.provider_config_key == provider_config_key)

    return query.order_by(db.OAuthConnection.created_at.desc()).all()


def update_oauth_connection_name(
    session: Session,
    connection_id: UUID,
    name: str,
) -> db.OAuthConnection | None:
    connection = get_oauth_connection_by_id(session, connection_id)
    if not connection:
        return None

    connection.name = name
    session.commit()
    session.refresh(connection)

    return connection


def soft_delete_oauth_connection(
    session: Session,
    connection_id: UUID,
) -> bool:
    connection = get_oauth_connection_by_id(session, connection_id)
    if not connection:
        return False

    connection.deleted_at = datetime.now()
    session.commit()

    return True
