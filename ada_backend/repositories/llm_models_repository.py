from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, case
from uuid import UUID
from typing import Optional

from ada_backend.database import models as db

PROVIDER_ORDER = {
    "openai": 1,
    "google": 2,
    "mistral": 3,
    "cerebras": 4,
}


def _get_provider_order(provider: str) -> int:
    return case({provider == k: v for k, v in PROVIDER_ORDER.items()}, else_=99)


def get_all_llm_models(session: Session) -> list[db.LLMModel]:

    return (
        session.query(db.LLMModel)
        .order_by(_get_provider_order(db.LLMModel.provider), db.LLMModel.display_name.asc())
        .options(joinedload(db.LLMModel.llm_cost))
        .all()
    )


def get_llm_models_by_capability(session: Session, capabilities: list[str]) -> list[db.LLMModel]:

    query = (
        session.query(db.LLMModel)
        .order_by(_get_provider_order(db.LLMModel.provider), db.LLMModel.display_name.asc())
        .options(joinedload(db.LLMModel.llm_cost))
    )

    if not capabilities:
        return query.all()

    filters = [db.LLMModel.model_capacity.contains([capability]) for capability in capabilities]
    query = query.filter(and_(*filters))

    return query.all()


def create_llm_model(
    session: Session,
    display_name: str,
    model_description: str,
    model_capacity: list[str],
    model_provider: str,
    model_name: str,
) -> db.LLMModel:
    llm_model = db.LLMModel(
        display_name=display_name,
        description=model_description,
        model_capacity=model_capacity,
        provider=model_provider,
        model_name=model_name,
    )
    session.add(llm_model)
    session.commit()
    return llm_model


def delete_llm_model(session: Session, llm_model_id: UUID) -> None:
    session.query(db.LLMModel).filter(db.LLMModel.id == llm_model_id).delete()
    session.commit()


def update_llm_model(
    session: Session,
    llm_model_id: UUID,
    display_name: str,
    model_name: str,
    description: str,
    model_capacity: list[str],
    provider: str,
) -> Optional[db.LLMModel]:
    existing_llm_model = session.query(db.LLMModel).filter(db.LLMModel.id == llm_model_id).first()
    if not existing_llm_model:
        return None
    if display_name is not None:
        existing_llm_model.display_name = display_name
    if model_name is not None:
        existing_llm_model.model_name = model_name
    if description is not None:
        existing_llm_model.description = description
    if model_capacity is not None:
        existing_llm_model.model_capacity = model_capacity
    if provider is not None:
        existing_llm_model.provider = provider
    session.commit()
    session.refresh(existing_llm_model)
    return existing_llm_model


def llm_model_exists(session: Session, model_name: str, provider: str, model_capacity: list[str]) -> bool:
    return (
        session.query(db.LLMModel)
        .filter(
            db.LLMModel.model_name == model_name,
            db.LLMModel.provider == provider,
            db.LLMModel.model_capacity == model_capacity,
        )
        .first()
        is not None
    )
