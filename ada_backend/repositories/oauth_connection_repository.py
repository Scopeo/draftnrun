"""
Repository for OAuth connections managed by Nango.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def create_oauth_connection(
    session: Session,
    project_id: UUID,
    provider_config_key: str,
    nango_connection_id: str,
    name: str = "",
    created_by_user_id: UUID | None = None,
) -> db.OAuthConnection:
    """
    Create a new OAuth connection.

    Args:
        session: Database session
        project_id: ID of the project this connection belongs to
        provider_config_key: Provider key (e.g., "slack", "google")
        nango_connection_id: UUID from Nango (source of truth for credentials)
        name: Display name for the connection (e.g., "Work Slack")
        created_by_user_id: User who created the connection

    Returns:
        Created OAuthConnection instance
    """
    connection = db.OAuthConnection(
        project_id=project_id,
        provider_config_key=provider_config_key,
        nango_connection_id=nango_connection_id,
        name=name,
        created_by_user_id=created_by_user_id,
    )
    session.add(connection)
    session.commit()
    session.refresh(connection)

    LOGGER.info(f"Created OAuth connection {connection.id} for project {project_id}, provider {provider_config_key}")

    return connection


def get_oauth_connection_by_id(
    session: Session,
    connection_id: UUID,
) -> db.OAuthConnection | None:
    """
    Get OAuth connection by ID.

    Excludes soft-deleted connections.
    """
    return (
        session.query(db.OAuthConnection)
        .filter(db.OAuthConnection.id == connection_id, db.OAuthConnection.deleted_at.is_(None))
        .first()
    )


def get_oauth_connection_by_nango_id(
    session: Session,
    nango_connection_id: str,
) -> db.OAuthConnection | None:
    """
    Get OAuth connection by Nango connection ID.

    Excludes soft-deleted connections.
    """
    return (
        session.query(db.OAuthConnection)
        .filter(db.OAuthConnection.nango_connection_id == nango_connection_id, db.OAuthConnection.deleted_at.is_(None))
        .first()
    )


def list_oauth_connections_by_project(
    session: Session,
    project_id: UUID,
    provider_config_key: str | None = None,
) -> list[db.OAuthConnection]:
    """
    List all OAuth connections for a project.

    Args:
        session: Database session
        project_id: Project ID
        provider_config_key: Optional provider filter (e.g., "slack")

    Returns:
        List of active OAuth connections
    """
    query = session.query(db.OAuthConnection).filter(
        db.OAuthConnection.project_id == project_id, db.OAuthConnection.deleted_at.is_(None)
    )

    if provider_config_key:
        query = query.filter(db.OAuthConnection.provider_config_key == provider_config_key)

    return query.order_by(db.OAuthConnection.created_at.desc()).all()


def update_oauth_connection_name(
    session: Session,
    connection_id: UUID,
    name: str,
) -> db.OAuthConnection | None:
    """
    Update the display name of an OAuth connection.

    Returns:
        Updated connection or None if not found
    """
    connection = get_oauth_connection_by_id(session, connection_id)
    if not connection:
        return None

    connection.name = name
    session.commit()
    session.refresh(connection)

    LOGGER.info(f"Updated OAuth connection {connection_id} name to '{name}'")

    return connection


def soft_delete_oauth_connection(
    session: Session,
    connection_id: UUID,
) -> bool:
    """
    Soft delete an OAuth connection.

    Returns:
        True if deleted, False if not found
    """
    connection = get_oauth_connection_by_id(session, connection_id)
    if not connection:
        return False

    connection.deleted_at = datetime.now()
    session.commit()

    LOGGER.info(f"Soft deleted OAuth connection {connection_id}")

    return True


def hard_delete_oauth_connection(
    session: Session,
    connection_id: UUID,
) -> bool:
    """
    Permanently delete an OAuth connection from database.

    Use with caution. Soft delete is preferred.

    Returns:
        True if deleted, False if not found
    """
    connection = session.query(db.OAuthConnection).filter(db.OAuthConnection.id == connection_id).first()

    if not connection:
        return False

    session.delete(connection)
    session.commit()

    LOGGER.info(f"Hard deleted OAuth connection {connection_id}")

    return True
