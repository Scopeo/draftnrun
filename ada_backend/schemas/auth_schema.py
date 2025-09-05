from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class OrganizationAccess(BaseModel):
    org_id: UUID
    role: str


class SupabaseUser(BaseModel):
    id: UUID
    email: str
    token: str


class ApiKeyData(BaseModel):
    key_id: UUID
    key_name: str


class ApiKeyGetResponse(BaseModel):
    project_id: Optional[UUID]
    organization_id: Optional[UUID]
    api_keys: list[ApiKeyData]


class ApiKeyCreateRequest(BaseModel):
    key_name: str
    project_id: UUID


class OrgApiKeyCreateRequest(BaseModel):
    key_name: str
    org_id: UUID


class ApiKeyCreatedResponse(BaseModel):
    private_key: str
    key_id: UUID


class ApiKeyDeleteRequest(BaseModel):
    key_id: UUID


class ApiKeyDeleteResponse(BaseModel):
    key_id: UUID
    message: str


class VerifiedApiKey(BaseModel):
    api_key_id: UUID
    scope_type: str
    project_id: Optional[UUID]
    organization_id: Optional[UUID]
