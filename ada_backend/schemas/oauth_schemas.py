from uuid import UUID

from pydantic import BaseModel

from engine.integrations.providers import OAuthProvider


class CreateOAuthConnectionRequest(BaseModel):
    provider_config_key: OAuthProvider
    end_user_email: str | None = None
    name: str = ""


class OAuthURLResponse(BaseModel):
    oauth_url: str
    end_user_id: str


class OAuthConnectionResponse(BaseModel):
    connection_id: UUID
    provider_config_key: str
    name: str


class OAuthConnectionStatusResponse(BaseModel):
    connected: bool
    provider_config_key: str
    connection_id: UUID | None = None
    name: str | None = None


# Service layer models (for internal use)
class OAuthAuthorizationResult(BaseModel):
    """Result from create_oauth_authorization service method."""

    oauth_url: str
    end_user_id: str
    expires_at: str


class OAuthConnectionStatus(BaseModel):
    """Result from check_connection_status service method."""

    connected: bool
    provider_config_key: str
    connection_id: UUID | None = None
    name: str | None = None
