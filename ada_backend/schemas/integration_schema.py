from pydantic import BaseModel
from uuid import UUID


class IntegrationSchema(BaseModel):
    id: UUID
    name: str
    service: str


class CreateComponentIntegrationSchema(BaseModel):
    integration_id: UUID
    access_token: str
    refresh_token: str
    expires_at: str
