from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from uuid import UUID


class IntegrationSchema(BaseModel):
    id: UUID
    name: str
    service: str


class GraphIntegrationSchema(IntegrationSchema):
    secret_id: Optional[UUID] = None


class CreateProjectIntegrationSchema(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_last_updated: Optional[datetime] = None


class IntegrationSecretResponse(BaseModel):
    integration_id: UUID
    secret_id: UUID
