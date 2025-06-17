from uuid import UUID

from pydantic import BaseModel


class OrganizationSecretResponse(BaseModel):
    organization: UUID
    secret_key: str


class OrganizationGetSecretKeysResponse(BaseModel):
    organization_id: UUID
    secret_keys: list[str]
