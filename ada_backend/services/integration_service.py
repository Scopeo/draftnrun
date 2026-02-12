import logging
from uuid import UUID, uuid4

from asyncache import cached
from cachetools import TTLCache
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories import integration_repository, oauth_connection_repository
from ada_backend.schemas.integration_schema import CreateProjectIntegrationSchema, IntegrationSecretResponse
from ada_backend.schemas.oauth_schemas import (
    OAuthAuthorizationResult,
    OAuthConnectionListItem,
    OAuthConnectionStatus,
)
from ada_backend.services.errors import (
    NangoConnectionNotFoundError,
    NangoTokenMissingError,
    OAuthConnectionNotFoundError,
    OAuthConnectionUnauthorizedError,
)
from ada_backend.services.nango_client import NangoClient, NangoClientError, get_nango_client
from engine.integrations.providers import OAuthProvider
from settings import settings

LOGGER = logging.getLogger(__name__)

_CACHE_EXPIRATION_MINUTES = 5
_NANGO_TOKEN_CACHE = TTLCache(maxsize=1000, ttl=_CACHE_EXPIRATION_MINUTES * 60)


def _generate_connection_name(provider_config_key: str, count: int) -> str:
    """
    Generate auto-name for OAuth connection.

    Format:
    - First connection: "{Provider} Connection"
    - Second+: "{Provider} Connection (N)"
    """
    provider_display = provider_config_key.title()
    if count == 1:
        return f"{provider_display} Connection"
    return f"{provider_display} Connection ({count})"


async def create_oauth_authorization(
    organization_id: UUID,
    provider_config_key: str | OAuthProvider,
    end_user_email: str | None = None,
) -> OAuthAuthorizationResult:
    """
    Start OAuth authorization flow with Nango (headless mode).

    Generates a direct OAuth URL to the provider without the Connect UI.
    Uses UUID as end_user_id so the same ID becomes the OAuthConnection PK on confirm.

    Flow:
    1. Generate pending_connection_id (UUID)
    2. Create connect session in Nango with end_user_id = str(pending_connection_id)
    3. Return oauth_url and pending_connection_id for frontend to pass to confirm

    Args:
        organization_id: The organization UUID
        provider_config_key: The OAuth provider (e.g., 'slack', 'hubspot')
        end_user_email: Optional email for pre-filling in the OAuth flow

    Returns:
        OAuthAuthorizationResult with oauth_url, pending_connection_id, and expires_at
    """
    LOGGER.info(f"Creating OAuth authorization for org {organization_id}, provider {provider_config_key}")

    pending_connection_id = uuid4()
    end_user_id = str(pending_connection_id)

    nango = get_nango_client()
    session_data = await nango.create_connect_session(
        end_user_id=end_user_id,
        end_user_email=end_user_email,
        allowed_integrations=[provider_config_key],
    )

    connect_session_token = session_data.get("token")
    if not connect_session_token:
        LOGGER.error(f"No connect_session_token in Nango response for org {organization_id}")
        raise ValueError("No connect_session_token in Nango response")

    nango_url = (settings.NANGO_PUBLIC_URL or settings.NANGO_INTERNAL_URL or "http://localhost:3003").rstrip("/")
    oauth_url = f"{nango_url}/oauth/connect/{provider_config_key}?connect_session_token={connect_session_token}"

    return OAuthAuthorizationResult(
        oauth_url=oauth_url,
        pending_connection_id=pending_connection_id,
        expires_at=session_data.get("expires_at", ""),
    )


async def confirm_oauth_connection(
    session: Session,
    organization_id: UUID,
    pending_connection_id: UUID,
    provider_config_key: str | OAuthProvider,
    created_by_user_id: UUID | None = None,
    name: str = "",
) -> db.OAuthConnection:
    """
    Confirm OAuth connection after user completes flow.

    Flow:
    1. Queries Nango using end_user_id = str(pending_connection_id) to find the connection
    2. Retrieves the Nango-generated connection_id
    3. Checks if we already have this connection in our database
    4. Creates OAuthConnection with id=pending_connection_id if it doesn't exist

    If name is empty, auto-generates based on provider and existing count
    (e.g., "Slack Connection", "Slack Connection (2)").

    Args:
        session: Database session
        organization_id: The organization UUID
        pending_connection_id: UUID from authorize response (used as end_user_id in Nango)
        provider_config_key: The OAuth provider (e.g., 'slack', 'hubspot')
        created_by_user_id: User who initiated the OAuth flow
        name: Optional friendly name for the connection (auto-generated if empty)

    Returns:
        OAuthConnection record (existing or newly created)

    Raises:
        NangoConnectionNotFoundError: If connection not found in Nango (OAuth flow incomplete)
    """
    LOGGER.info(f"Confirming OAuth connection for org {organization_id}, provider {provider_config_key}")

    nango = get_nango_client()
    end_user_id = str(pending_connection_id)

    connections = await nango.list_connections(
        provider_config_key=str(provider_config_key),
        end_user_id=end_user_id,
    )

    if not connections:
        LOGGER.warning(f"No connections found in Nango for org {organization_id}, provider {provider_config_key}")
        raise NangoConnectionNotFoundError(organization_id=organization_id, provider=str(provider_config_key))

    connection = connections[0]
    real_nango_connection_id = connection["connection_id"]

    existing_connection = oauth_connection_repository.get_oauth_connection_by_nango_id(
        session, real_nango_connection_id
    )

    if existing_connection:
        return existing_connection

    provider_key = str(provider_config_key)
    if not name or not name.strip():
        existing_count = oauth_connection_repository.count_connections_by_provider(
            session=session,
            organization_id=organization_id,
            provider_config_key=provider_key,
        )
        name = _generate_connection_name(provider_config_key=provider_key, count=existing_count + 1)
        LOGGER.info(f"Auto-generated connection name: {name}")

    new_connection = oauth_connection_repository.create_oauth_connection(
        session=session,
        connection_id=pending_connection_id,
        organization_id=organization_id,
        provider_config_key=provider_key,
        nango_connection_id=real_nango_connection_id,
        name=name,
        created_by_user_id=created_by_user_id,
    )

    LOGGER.info(f"Created new OAuth connection {new_connection.id} for org {organization_id}")
    return new_connection


async def check_connection_status(
    session: Session,
    organization_id: UUID,
    connection_id: UUID,
    provider_config_key: str | OAuthProvider,
) -> OAuthConnectionStatus:
    """
    Check if a specific OAuth connection is active.

    Flow:
    1. Fetch connection by ID
    2. Verify it belongs to the organization (prevents IDOR)
    3. Check if it still exists and is valid in Nango

    Args:
        session: Database session
        organization_id: The organization UUID (for ownership verification)
        connection_id: The OAuthConnection ID to check
        provider_config_key: The OAuth provider (e.g., 'slack', 'hubspot')

    Returns:
        OAuthConnectionStatus with connected, provider_config_key, connection_id, and name
    """
    connection = oauth_connection_repository.get_oauth_connection_by_id(session, connection_id)

    if not connection or connection.organization_id != organization_id:
        return OAuthConnectionStatus(
            connected=False,
            provider_config_key=str(provider_config_key),
            connection_id=None,
        )

    try:
        nango = get_nango_client()
        nango_connection = await nango.get_connection(
            provider_config_key=str(provider_config_key),
            connection_id=connection.nango_connection_id,
        )

        if not nango_connection:
            return OAuthConnectionStatus(
                connected=False,
                provider_config_key=str(provider_config_key),
                connection_id=None,
            )

        return OAuthConnectionStatus(
            connected=True,
            provider_config_key=str(provider_config_key),
            connection_id=connection.id,
            name=connection.name,
        )

    except NangoClientError as e:
        LOGGER.warning(f"Failed to check Nango connection: {e}")
        return OAuthConnectionStatus(
            connected=False,
            provider_config_key=str(provider_config_key),
            connection_id=None,
        )


async def revoke_oauth_connection(
    session: Session,
    organization_id: UUID,
    connection_id: UUID,
    provider_config_key: str | OAuthProvider,
) -> None:
    """
    Revoke OAuth connection.

    Flow:
    1. Retrieves the connection from our database
    2. Verifies the connection belongs to the specified organization (prevents IDOR)
    3. Attempts to delete it from Nango (gracefully handles if already deleted)
    4. Soft-deletes the connection record from our database

    Args:
        session: Database session
        organization_id: UUID of the organization (for ownership verification)
        connection_id: UUID of the OAuthConnection to revoke
        provider_config_key: The OAuth provider (e.g., 'slack', 'hubspot')

    Raises:
        OAuthConnectionNotFoundError: If connection not found
        OAuthConnectionUnauthorizedError: If connection doesn't belong to the organization
    """
    LOGGER.info(f"Revoking OAuth connection {connection_id} for org {organization_id}")

    connection = oauth_connection_repository.get_oauth_connection_by_id(session, connection_id)

    if not connection:
        raise OAuthConnectionNotFoundError(connection_id=connection_id)

    if connection.organization_id != organization_id:
        LOGGER.warning(
            f"Unauthorized revocation attempt: connection {connection_id} does not belong to org {organization_id}"
        )
        raise OAuthConnectionUnauthorizedError(connection_id=connection_id, organization_id=organization_id)

    try:
        nango = get_nango_client()
        await nango.delete_connection(
            provider_config_key=str(provider_config_key),
            connection_id=connection.nango_connection_id,
        )
    except NangoClientError as e:
        LOGGER.warning(f"Failed to delete Nango connection (may already be deleted): {e}")

    oauth_connection_repository.soft_delete_oauth_connection(session, connection_id)


async def update_oauth_connection_name(
    session: Session,
    organization_id: UUID,
    connection_id: UUID,
    new_name: str,
) -> db.OAuthConnection:
    """
    Update OAuth connection display name.
    Validates ownership via organization_id (prevents IDOR).
    """
    connection = oauth_connection_repository.get_oauth_connection_by_id(session, connection_id)

    if not connection or connection.organization_id != organization_id:
        raise OAuthConnectionNotFoundError(connection_id=connection_id)

    updated = oauth_connection_repository.update_oauth_connection_name(
        session=session, connection_id=connection_id, name=new_name
    )
    if not updated:
        raise OAuthConnectionNotFoundError(connection_id=connection_id)

    LOGGER.info(f"Updated connection {connection_id} name to: {new_name}")
    return updated


def list_oauth_connections(
    session: Session,
    organization_id: UUID,
    provider_config_key: str | None = None,
) -> list[OAuthConnectionListItem]:
    """
    List OAuth connections for an organization.

    Args:
        session: Database session
        organization_id: The organization UUID
        provider_config_key: Optional filter by provider

    Returns:
        List of OAuthConnectionListItem
    """
    connections = oauth_connection_repository.list_oauth_connections_by_organization(
        session=session,
        organization_id=organization_id,
        provider_config_key=provider_config_key,
    )
    return [
        OAuthConnectionListItem(
            id=c.id,
            name=c.name,
            provider_config_key=c.provider_config_key,
            created_at=c.created_at,
            created_by_user_id=c.created_by_user_id,
        )
        for c in connections
    ]


@cached(
    cache=_NANGO_TOKEN_CACHE,
    key=lambda session, oauth_connection_id, provider_config_key: (str(oauth_connection_id), provider_config_key),
)
async def get_oauth_access_token(
    session: Session,
    oauth_connection_id: UUID,
    provider_config_key: str | OAuthProvider,
) -> str:
    """
    Get OAuth access token from Nango.
    Caches the access token for 5 minutes using (oauth_connection_id, provider_config_key) as the key.

    Args:
        session: Database session
        oauth_connection_id: ID of the OAuthConnection
        provider_config_key: Nango provider config key (e.g., "slack", "google")

    Returns:
        Valid access token from Nango

    Raises:
        ValueError: If connection not found or Nango connection invalid
    """
    connection = oauth_connection_repository.get_oauth_connection_by_id(session, oauth_connection_id)
    if not connection:
        raise OAuthConnectionNotFoundError(connection_id=oauth_connection_id)

    # TODO: Refactor entity factories to be async so we can use the singleton.
    nango = NangoClient()
    nango_connection = await nango.get_connection(
        provider_config_key=str(provider_config_key),
        connection_id=connection.nango_connection_id,
    )

    if not nango_connection:
        raise OAuthConnectionNotFoundError(connection_id=oauth_connection_id)

    credentials = nango_connection.get("credentials", {})
    access_token = credentials.get("access_token")
    if not access_token:
        LOGGER.error(f"Access token not found for connection {oauth_connection_id}")
        raise NangoTokenMissingError(connection_id=oauth_connection_id)

    return access_token


async def add_integration_secrets_service(
    session: Session,
    integration_id: UUID,
    create_project_integration: CreateProjectIntegrationSchema,
) -> IntegrationSecretResponse:
    integration_secret = integration_repository.insert_secret_integration(
        session=session,
        integration_id=integration_id,
        access_token=create_project_integration.access_token,
        refresh_token=create_project_integration.refresh_token,
        expires_in=create_project_integration.expires_in,
        token_last_updated=create_project_integration.token_last_updated,
    )
    return IntegrationSecretResponse(
        integration_id=integration_id,
        secret_id=integration_secret.id,
    )
