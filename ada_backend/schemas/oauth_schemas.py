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
