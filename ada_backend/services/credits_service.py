from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List
from ada_backend.schemas.credits_schema import (
    ComponentVersionCostResponse,
    OrganizationLimitResponse,
)
from ada_backend.repositories.credits_repository import (
    upsert_component_version_cost,
    delete_component_version_cost,
    create_organization_limit,
    update_organization_limit,
    delete_organization_limit,
    get_all_organization_limits,
)
from ada_backend.services.errors import (
    ComponentVersionCostNotFound,
    OrganizationLimitNotFound,
)


def upsert_component_version_cost_service(
    session: Session,
    component_version_id: UUID,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
) -> ComponentVersionCostResponse:
    component_cost = upsert_component_version_cost(
        session,
        component_version_id,
        credits_per_input_token,
        credits_per_output_token,
        credits_per_call,
        credits_per_second,
    )
    if component_cost is None:
        raise ComponentVersionCostNotFound(component_version_id)
    return ComponentVersionCostResponse.model_validate(component_cost, from_attributes=True)


def delete_component_version_cost_service(session: Session, component_version_id: UUID) -> None:
    return delete_component_version_cost(session, component_version_id)


def get_all_organization_limits_service(session: Session, year: int, month: int) -> List[OrganizationLimitResponse]:
    organization_limits = get_all_organization_limits(session, year, month)
    return [
        OrganizationLimitResponse.model_validate(organization_limit, from_attributes=True)
        for organization_limit in organization_limits
    ]


def create_organization_limit_service(
    session: Session,
    organization_id: UUID,
    year: int,
    month: int,
    limit: float,
) -> OrganizationLimitResponse:
    organization_limit = create_organization_limit(
        session,
        organization_id,
        year,
        month,
        limit,
    )
    return OrganizationLimitResponse.model_validate(organization_limit, from_attributes=True)


def update_organization_limit_service(
    session: Session,
    id: UUID,
    organization_id: UUID,
    limit: float,
) -> OrganizationLimitResponse:
    organization_limit = update_organization_limit(
        session,
        id=id,
        organization_id=organization_id,
        limit=limit,
    )
    if organization_limit is None:
        raise OrganizationLimitNotFound(id, organization_id)
    return OrganizationLimitResponse.model_validate(organization_limit, from_attributes=True)


def delete_organization_limit_service(
    session: Session,
    id: UUID,
    organization_id: UUID,
) -> None:
    return delete_organization_limit(session, id, organization_id)
