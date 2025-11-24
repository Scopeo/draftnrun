from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List

import ada_backend.database.models as db


def create_llm_cost(
    session: Session,
    llm_model_id: UUID,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
) -> db.LLMCost:

    llm_cost = db.LLMCost(
        llm_model_id=llm_model_id,
        credits_per_input_token=credits_per_input_token,
        credits_per_output_token=credits_per_output_token,
        credits_per_call=credits_per_call,
        credits_per_second=credits_per_second,
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
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
) -> db.LLMCost:
    llm_cost = session.query(db.LLMCost).filter(db.LLMCost.llm_model_id == llm_model_id).first()

    if llm_cost is None:
        raise ValueError(f"LLM cost with model id {llm_model_id} not found")

    if credits_per_input_token is not None:
        llm_cost.credits_per_input_token = credits_per_input_token
    if credits_per_output_token is not None:
        llm_cost.credits_per_output_token = credits_per_output_token
    if credits_per_call is not None:
        llm_cost.credits_per_call = credits_per_call
    if credits_per_second is not None:
        llm_cost.credits_per_second = credits_per_second
    session.commit()
    session.refresh(llm_cost)
    return llm_cost


def delete_llm_cost(session: Session, llm_model_id: UUID) -> None:
    llm_cost = session.query(db.LLMCost).filter(db.LLMCost.llm_model_id == llm_model_id).first()
    if llm_cost is None:
        raise ValueError(f"LLM cost with model id {llm_model_id} not found")
    session.delete(llm_cost)
    session.commit()


def create_component_version_cost(
    session: Session,
    component_version_id: UUID,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
) -> db.ComponentCost:

    component_cost = db.ComponentCost(
        component_version_id=component_version_id,
        credits_per_call=credits_per_call,
        credits_per_second=credits_per_second,
        credits_per_input_token=credits_per_input_token,
        credits_per_output_token=credits_per_output_token,
    )
    session.add(component_cost)
    session.commit()
    session.refresh(component_cost)
    return component_cost


def upsert_component_version_cost(
    session: Session,
    component_version_id: UUID,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
) -> db.ComponentCost:

    component_cost = (
        session.query(db.ComponentCost).filter(db.ComponentCost.component_version_id == component_version_id).first()
    )

    if component_cost is None:
        # Create new cost
        component_cost = create_component_version_cost(
            session,
            component_version_id,
            credits_per_call,
            credits_per_second,
            credits_per_input_token,
            credits_per_output_token,
        )
    else:
        # Update existing cost
        if credits_per_call is not None:
            component_cost.credits_per_call = credits_per_call
        if credits_per_second is not None:
            component_cost.credits_per_second = credits_per_second
        if credits_per_input_token is not None:
            component_cost.credits_per_input_token = credits_per_input_token
        if credits_per_output_token is not None:
            component_cost.credits_per_output_token = credits_per_output_token
        session.commit()
        session.refresh(component_cost)

    return component_cost


def delete_component_version_cost(session: Session, component_version_id: UUID) -> None:
    component_cost = (
        session.query(db.ComponentCost).filter(db.ComponentCost.component_version_id == component_version_id).first()
    )
    if component_cost is None:
        raise ValueError(f"Component version cost with id {component_version_id} not found")
    session.delete(component_cost)
    session.commit()


def get_all_organization_limits(session: Session, year: int, month: int) -> List[db.OrganizationLimit]:
    return (
        session.query(db.OrganizationLimit)
        .filter(db.OrganizationLimit.year == year, db.OrganizationLimit.month == month)
        .all()
    )


def create_organization_limit(
    session: Session,
    organization_id: UUID,
    year: int,
    month: int,
    limit: float,
) -> db.OrganizationLimit:
    organization_limit = db.OrganizationLimit(
        organization_id=organization_id,
        year=year,
        month=month,
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
        raise ValueError(f"Organization limit with id {id} and organization id {organization_id} not found")
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
    if organization_limit is None:
        raise ValueError(f"Organization limit with id {id} and organization id {organization_id} not found")
    session.delete(organization_limit)
    session.commit()
