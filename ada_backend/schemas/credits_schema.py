from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional


class OrganizationLimit(BaseModel):
    limit: Optional[float] = 0.0
    year: int
    month: int


class OrganizationLimitResponse(OrganizationLimit):

    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ComponentVersionCost(BaseModel):
    credits_per_second: Optional[float] = None
    credits_per_call: Optional[float] = None
    credits_per_input_token: Optional[float] = None
    credits_per_output_token: Optional[float] = None


class ComponentVersionCostResponse(ComponentVersionCost):
    id: UUID
    component_version_id: UUID
