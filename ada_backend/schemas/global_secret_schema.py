from datetime import datetime

from pydantic import BaseModel, Field


class GlobalSecretListItem(BaseModel):
    key: str
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)
    is_set: bool = True


class UpsertGlobalSecretRequest(BaseModel):
    key: str
    secret: str
