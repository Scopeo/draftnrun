from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.credits_repository import (
    create_organization_limit,
    delete_component_version_cost,
    delete_organization_limit,
    get_all_organization_limits_with_usage,
    update_organization_limit,
    upsert_component_version_cost,
)
from ada_backend.schemas.credits_schema import (
    ComponentVersionCostResponse,
    OrganizationLimitAndUsageResponse,
    OrganizationLimitResponse,
)
from ada_backend.services.errors import ComponentVersionCostNotFound, OrganizationLimitNotFound


def upsert_component_version_cost_service(
    session: Session,
    component_version_id: UUID,
    credits_per_call: Optional[float] = None,
    credits_per: Optional[dict] = None,
) -> ComponentVersionCostResponse:
    component_cost = upsert_component_version_cost(
        session,
        component_version_id,
        credits_per_call,
        credits_per,
    )
    if component_cost is None:
        raise ComponentVersionCostNotFound(component_version_id)
    return ComponentVersionCostResponse.model_validate(component_cost, from_attributes=True)


def delete_component_version_cost_service(session: Session, component_version_id: UUID) -> None:
    return delete_component_version_cost(session, component_version_id)


def create_organization_limit_service(
    session: Session,
    organization_id: UUID,
    limit: float,
) -> OrganizationLimitResponse:
    organization_limit = create_organization_limit(
        session,
        organization_id,
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


def get_all_organization_limits_and_usage_service(
    session: Session, month: int, year: int
) -> list[OrganizationLimitAndUsageResponse]:
    organization_limits_and_usage = get_all_organization_limits_with_usage(session, month, year)
    return [
        OrganizationLimitAndUsageResponse.model_validate(organization_limit_and_usage, from_attributes=True)
        for organization_limit_and_usage in organization_limits_and_usage
    ]
