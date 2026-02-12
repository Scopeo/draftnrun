from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from engine.integrations.providers import OAuthProvider


class CreateOAuthConnectionRequest(BaseModel):
    provider_config_key: OAuthProvider
    end_user_email: str | None = None
    name: str = ""
    pending_connection_id: UUID | None = None


class UpdateOAuthConnectionRequest(BaseModel):
    name: str = Field(..., min_length=1)


class OAuthURLResponse(BaseModel):
    oauth_url: str
    pending_connection_id: UUID


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
    pending_connection_id: UUID
    expires_at: str


class OAuthConnectionListItem(BaseModel):
    id: UUID
    name: str
    provider_config_key: str
    created_at: datetime
    created_by_user_id: UUID | None = None


class OAuthConnectionStatus(BaseModel):
    """Result from check_connection_status service method."""

    connected: bool
    provider_config_key: str
    connection_id: UUID | None = None
    name: str | None = None
