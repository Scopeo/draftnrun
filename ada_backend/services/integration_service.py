import logging
from uuid import UUID

from asyncache import cached
from cachetools import TTLCache
from sqlalchemy.orm import Session

from ada_backend.repositories import integration_repository, oauth_connection_repository
from ada_backend.schemas.integration_schema import CreateProjectIntegrationSchema, IntegrationSecretResponse
from ada_backend.services.nango_client import NangoClientError, get_nango_client
from engine.integrations.providers import OAuthProvider
from settings import settings

LOGGER = logging.getLogger(__name__)

_CACHE_EXPIRATION_MINUTES = 5
_NANGO_TOKEN_CACHE = TTLCache(maxsize=1000, ttl=_CACHE_EXPIRATION_MINUTES * 60)


def generate_nango_end_user_id(project_id: UUID, provider_config_key: str) -> str:
    """
    Generate Nango end_user_id for OAuth connections.

    Format: proj_{project_id}_{provider_config_key}

    Current limitation: This deterministic ID enforces 1 connection per provider per project.
    """
    return f"proj_{project_id}_{provider_config_key}"


async def create_oauth_authorization(
    project_id: UUID,
    provider_config_key: str | OAuthProvider,
    end_user_email: str | None = None,
) -> dict:
    """
    Start OAuth authorization flow with Nango (headless mode).

    Generates a direct OAuth URL to the provider without the Connect UI.

    Flow:
    1. Creates a connect session in Nango to obtain a temporary token
    2. Constructs the direct OAuth URL using the token
    3. Returns the OAuth URL that the user should visit to authorize

    Args:
        project_id: The project UUID
        provider_config_key: The OAuth provider (e.g., 'slack', 'hubspot')
        end_user_email: Optional email for pre-filling in the OAuth flow

    Returns:
        dict with 'oauth_url', 'end_user_id', and 'expires_at'
    """

    nango = get_nango_client()
    end_user_id = generate_nango_end_user_id(project_id, str(provider_config_key))

    session_data = await nango.create_connect_session(
        end_user_id=end_user_id,
        end_user_email=end_user_email,
        allowed_integrations=[provider_config_key],
    )

    connect_session_token = session_data.get("token")
    if not connect_session_token:
        raise ValueError("No connect_session_token in Nango response")

    nango_url = (settings.NANGO_PUBLIC_URL or settings.NANGO_INTERNAL_URL or "http://localhost:3003").rstrip("/")
    oauth_url = f"{nango_url}/oauth/connect/{provider_config_key}?connect_session_token={connect_session_token}"

    return {
        "oauth_url": oauth_url,
        "end_user_id": end_user_id,
        "expires_at": session_data.get("expires_at", ""),
    }


async def confirm_oauth_connection(
    session: Session,
    project_id: UUID,
    provider_config_key: str | OAuthProvider,
    created_by_user_id: UUID | None = None,
    name: str = "",
) -> UUID:
    """
    Confirm OAuth connection after user completes flow.

    Flow:
    1. Queries Nango using our custom end_user_id to find the connection
    2. Retrieves the Nango-generated connection_id (UUID)
    3. Checks if we already have this connection in our database
    4. Creates a new OAuthConnection record if it doesn't exist

    Args:
        session: Database session
        project_id: The project UUID
        provider_config_key: The OAuth provider (e.g., 'slack', 'hubspot')
        created_by_user_id: User who initiated the OAuth flow
        name: Optional friendly name for the connection

    Returns:
        UUID of the OAuthConnection record

    Raises:
        ValueError: If connection not found in Nango (OAuth flow incomplete)
    """
    nango = get_nango_client()
    end_user_id = generate_nango_end_user_id(project_id, str(provider_config_key))

    connections = await nango.list_connections(
        provider_config_key=str(provider_config_key),
        end_user_id=end_user_id,
    )

    if not connections:
        raise ValueError("Connection not found in Nango. OAuth flow may not be complete.")

    connection = connections[0]
    real_nango_connection_id = connection["connection_id"]

    existing_connection = oauth_connection_repository.get_oauth_connection_by_nango_id(
        session, real_nango_connection_id
    )

    if existing_connection:
        return existing_connection.id

    new_connection = oauth_connection_repository.create_oauth_connection(
        session=session,
        project_id=project_id,
        provider_config_key=str(provider_config_key),
        nango_connection_id=real_nango_connection_id,
        name=name,
        created_by_user_id=created_by_user_id,
    )

    return new_connection.id


async def check_connection_status(
    session: Session,
    project_id: UUID,
    provider_config_key: str | OAuthProvider,
) -> dict:
    """
    Check if OAuth connection is active for a project.

    Flow:
    1. Queries our database for connections matching project and provider
    2. Verifies the most recent connection still exists in Nango
    3. Returns connection status with metadata

    Args:
        session: Database session
        project_id: The project UUID
        provider_config_key: The OAuth provider (e.g., 'slack', 'hubspot')

    Returns:
        dict with 'connected' (bool), 'provider_config_key' (str),
        'connection_id' (str | None), and 'name' (str | None)
    """
    connections = oauth_connection_repository.list_oauth_connections_by_project(
        session=session,
        project_id=project_id,
        provider_config_key=str(provider_config_key),
    )

    if not connections:
        return {
            "connected": False,
            "provider_config_key": str(provider_config_key),
            "connection_id": None,
        }

    connection = connections[0]

    try:
        nango = get_nango_client()
        nango_connection = await nango.get_connection(
            provider_config_key=str(provider_config_key),
            connection_id=connection.nango_connection_id,
        )

        if not nango_connection:
            return {
                "connected": False,
                "provider_config_key": str(provider_config_key),
                "connection_id": None,
            }

        return {
            "connected": True,
            "provider_config_key": str(provider_config_key),
            "connection_id": str(connection.id),
            "name": connection.name,
        }

    except NangoClientError as e:
        LOGGER.warning(f"Failed to check Nango connection: {e}")
        return {
            "connected": False,
            "provider_config_key": str(provider_config_key),
            "connection_id": None,
        }


async def revoke_oauth_connection(
    session: Session,
    project_id: UUID,
    connection_id: UUID,
    provider_config_key: str | OAuthProvider,
) -> None:
    """
    Revoke OAuth connection.

    Flow:
    1. Retrieves the connection from our database
    2. Verifies the connection belongs to the specified project (prevents IDOR)
    3. Attempts to delete it from Nango (gracefully handles if already deleted)
    4. Soft-deletes the connection record from our database

    Args:
        session: Database session
        project_id: UUID of the project (for ownership verification)
        connection_id: UUID of the OAuthConnection to revoke
        provider_config_key: The OAuth provider (e.g., 'slack', 'hubspot')

    Raises:
        ValueError: If connection not found or doesn't belong to the project
    """
    connection = oauth_connection_repository.get_oauth_connection_by_id(session, connection_id)

    if not connection:
        raise ValueError("OAuth connection not found")

    if connection.project_id != project_id:
        raise ValueError("OAuth connection does not belong to this project")

    try:
        nango = get_nango_client()
        await nango.delete_connection(
            provider_config_key=str(provider_config_key),
            connection_id=connection.nango_connection_id,
        )
    except NangoClientError as e:
        LOGGER.warning(f"Failed to delete Nango connection (may already be deleted): {e}")

    oauth_connection_repository.soft_delete_oauth_connection(session, connection_id)


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
        raise ValueError(f"OAuth connection with ID {oauth_connection_id} not found.")

    nango = get_nango_client()
    nango_connection = await nango.get_connection(
        provider_config_key=str(provider_config_key),
        connection_id=connection.nango_connection_id,
    )

    if not nango_connection:
        raise ValueError(f"Nango connection not found for {connection.nango_connection_id}")

    credentials = nango_connection.get("credentials", {})
    access_token = credentials.get("access_token")
    if not access_token:
        raise ValueError("Access token not found in Nango connection credentials")

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
