from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, literal
from sqlalchemy.orm import Session

import ada_backend.database.models as db


@dataclass
class OrganizationLimitAndUsageDTO:
    organization_id: UUID
    limit_id: Optional[UUID] = None
    limit: Optional[float] = None
    total_credits_used: Optional[float] = None


def _update_cost_fields(
    cost_obj: db.Cost,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
    credits_per_call: Optional[float] = None,
    credits_per: Optional[dict] = None,
) -> None:
    """Helper function to update cost fields on a Cost object."""

    cost_obj.credits_per_input_token = credits_per_input_token
    cost_obj.credits_per_output_token = credits_per_output_token
    cost_obj.credits_per_call = credits_per_call
    cost_obj.credits_per = credits_per


def create_llm_cost(
    session: Session,
    llm_model_id: UUID,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
) -> db.LLMCost:
    llm_cost = db.LLMCost(
        llm_model_id=llm_model_id,
        credits_per_input_token=credits_per_input_token,
        credits_per_output_token=credits_per_output_token,
    )
    session.add(llm_cost)
    session.commit()
    session.refresh(llm_cost)
    return llm_cost


def update_llm_cost(
    session: Session,
    llm_model_id: UUID,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
) -> db.LLMCost:
    llm_cost = session.query(db.LLMCost).filter(db.LLMCost.llm_model_id == llm_model_id).first()

    _update_cost_fields(
        cost_obj=llm_cost,
        credits_per_input_token=credits_per_input_token,
        credits_per_output_token=credits_per_output_token,
    )
    session.commit()
    session.refresh(llm_cost)
    return llm_cost


def delete_llm_cost(session: Session, llm_model_id: UUID) -> None:
    llm_cost = session.query(db.LLMCost).filter(db.LLMCost.llm_model_id == llm_model_id).first()
    if llm_cost is not None:
        session.delete(llm_cost)
        session.commit()


def upsert_llm_cost(
    session: Session,
    llm_model_id: UUID,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
) -> db.LLMCost:
    llm_cost = session.query(db.LLMCost).filter(db.LLMCost.llm_model_id == llm_model_id).first()

    if llm_cost is None:
        llm_cost = create_llm_cost(
            session,
            llm_model_id,
            credits_per_input_token,
            credits_per_output_token,
        )
    else:
        _update_cost_fields(
            cost_obj=llm_cost,
            credits_per_input_token=credits_per_input_token,
            credits_per_output_token=credits_per_output_token,
        )
        session.commit()
        session.refresh(llm_cost)

    return llm_cost


def create_component_version_cost(
    session: Session,
    component_version_id: UUID,
    credits_per_call: Optional[float] = None,
    credits_per: Optional[dict] = None,
) -> db.ComponentCost:
    component_cost = db.ComponentCost(
        component_version_id=component_version_id,
        credits_per_call=credits_per_call,
        credits_per=credits_per,
    )
    session.add(component_cost)
    session.commit()
    session.refresh(component_cost)
    return component_cost


def upsert_component_version_cost(
    session: Session,
    component_version_id: UUID,
    credits_per_call: Optional[float] = None,
    credits_per: Optional[dict] = None,
) -> db.ComponentCost:
    component_cost = (
        session.query(db.ComponentCost).filter(db.ComponentCost.component_version_id == component_version_id).first()
    )

    if component_cost is None:
        component_cost = create_component_version_cost(
            session,
            component_version_id,
            credits_per_call,
            credits_per,
        )
    else:
        _update_cost_fields(
            cost_obj=component_cost,
            credits_per_call=credits_per_call,
            credits_per=credits_per,
        )
        session.commit()
        session.refresh(component_cost)

    return component_cost


def delete_component_version_cost(session: Session, component_version_id: UUID) -> None:
    component_cost = (
        session.query(db.ComponentCost).filter(db.ComponentCost.component_version_id == component_version_id).first()
    )
    if component_cost is not None:
        session.delete(component_cost)
        session.commit()


def create_organization_limit(
    session: Session,
    organization_id: UUID,
    limit: float,
) -> db.OrganizationLimit:
    organization_limit = db.OrganizationLimit(
        organization_id=organization_id,
        limit=limit,
    )
    session.add(organization_limit)
    session.commit()
    session.refresh(organization_limit)
    return organization_limit


def update_organization_limit(
    session: Session,
    id: UUID,
    organization_id: UUID,
    limit: float,
) -> db.OrganizationLimit:
    organization_limit = (
        session.query(db.OrganizationLimit)
        .filter(
            db.OrganizationLimit.id == id,
            db.OrganizationLimit.organization_id == organization_id,
        )
        .first()
    )

    if organization_limit is None:
        return None

    organization_limit.limit = limit
    session.commit()
    session.refresh(organization_limit)
    return organization_limit


def delete_organization_limit(session: Session, id: UUID, organization_id: UUID) -> None:
    organization_limit = (
        session.query(db.OrganizationLimit)
        .filter(
            db.OrganizationLimit.id == id,
            db.OrganizationLimit.organization_id == organization_id,
        )
        .first()
    )
    session.delete(organization_limit)
    session.commit()


def get_organization_limit(
    session: Session,
    organization_id: UUID,
) -> Optional[db.OrganizationLimit]:
    """Get organization limit for a specific year and month."""
    organization_limit = (
        session.query(db.OrganizationLimit)
        .filter(
            db.OrganizationLimit.organization_id == organization_id,
        )
        .first()
    )
    if organization_limit is None:
        return None
    return organization_limit


def get_organization_total_credits(session: Session, organization_id: UUID, year: int, month: int) -> float:
    """Get total credits for all projects in an organization for a specific year and month."""
    total = (
        session.query(func.sum(db.Usage.credits_used))
        .join(db.Project, db.Project.id == db.Usage.project_id)
        .filter(db.Project.organization_id == organization_id, db.Usage.year == year, db.Usage.month == month)
        .scalar()
    )
    return round(float(total) if total else 0.0, 2)


def get_all_organization_limits_with_usage(
    session: Session, month: int, year: int
) -> List[OrganizationLimitAndUsageDTO]:
    usage_subquery = (
        session.query(
            db.Project.organization_id.label("org_id"),
            func.sum(db.Usage.credits_used).label("total_credits_used"),
        )
        .select_from(db.Usage)
        .join(db.Project, db.Usage.project_id == db.Project.id)
        .filter(db.Usage.year == year, db.Usage.month == month)
        .group_by(db.Project.organization_id)
        .subquery()
    )

    limits_query = session.query(
        db.OrganizationLimit.organization_id,
        db.OrganizationLimit.id.label("limit_id"),
        db.OrganizationLimit.limit,
        usage_subquery.c.total_credits_used,
    ).outerjoin(usage_subquery, db.OrganizationLimit.organization_id == usage_subquery.c.org_id)

    usage_only_query = (
        session.query(
            usage_subquery.c.org_id.label("organization_id"),
            literal(None).label("limit_id"),
            literal(None).label("limit"),
            usage_subquery.c.total_credits_used,
        )
        .select_from(usage_subquery)
        .outerjoin(db.OrganizationLimit, usage_subquery.c.org_id == db.OrganizationLimit.organization_id)
        .filter(db.OrganizationLimit.id.is_(None))
    )

    limits_and_usage_query = limits_query.union(usage_only_query)
    limit_usage_rows = limits_and_usage_query.all()

    return [
        OrganizationLimitAndUsageDTO(
            organization_id=row.organization_id,
            limit_id=row.limit_id,
            limit=row.limit,
            total_credits_used=(
                round(float(row.total_credits_used), 2) if row.total_credits_used is not None else None
            ),
        )
        for row in limit_usage_rows
    ]
