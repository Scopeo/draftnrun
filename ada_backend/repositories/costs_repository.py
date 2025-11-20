from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

import ada_backend.database.models as db


def get_usage_by_project_id(session: Session, project_id: UUID) -> list[db.Usage]:
    """Get all usage records for a project."""
    return session.query(db.Usage).filter(db.Usage.project_id == project_id).all()


def get_usage_by_project_id_and_year_and_month(
    session: Session, project_id: UUID, year: int, month: int
) -> db.Usage | None:
    """Get usage record for a project in a specific year and month."""
    return (
        session.query(db.Usage)
        .filter(db.Usage.project_id == project_id, db.Usage.year == year, db.Usage.month == month)
        .first()
    )


def create_llm_cost(
    session: Session,
    llm_model_id: UUID,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
) -> db.LLMCost:
    """
    Create a cost configuration for an LLM model.
    SQLAlchemy's joined table inheritance will automatically insert into both
    the costs table and llm_costs table.
    """
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


def create_component_cost(
    session: Session,
    component_id: UUID,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
) -> db.ComponentCost:
    """
    Create a cost configuration for a component.
    SQLAlchemy's joined table inheritance will automatically insert into both
    the costs table and component_costs table.
    """
    component_cost = db.ComponentCost(
        component_id=component_id,
        credits_per_call=credits_per_call,
        credits_per_second=credits_per_second,
        credits_per_input_token=credits_per_input_token,
        credits_per_output_token=credits_per_output_token,
    )
    session.add(component_cost)
    session.commit()
    session.refresh(component_cost)
    return component_cost


def create_parameter_value_cost(
    session: Session,
    component_parameter_definition_id: UUID,
    parameter_value: str,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
) -> db.ParameterValueCost:
    """
    Create a cost configuration for a parameter value.
    SQLAlchemy's joined table inheritance will automatically insert into both
    the costs table and parameter_value_costs table.
    """
    parameter_value_cost = db.ParameterValueCost(
        component_parameter_definition_id=component_parameter_definition_id,
        parameter_value=parameter_value,
        credits_per_call=credits_per_call,
        credits_per_second=credits_per_second,
        credits_per_input_token=credits_per_input_token,
        credits_per_output_token=credits_per_output_token,
    )
    session.add(parameter_value_cost)
    session.commit()
    session.refresh(parameter_value_cost)
    return parameter_value_cost
