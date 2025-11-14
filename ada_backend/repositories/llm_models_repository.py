from sqlalchemy.orm import Session
from uuid import UUID

from ada_backend.database import models as db


def get_all_llm_models(session: Session) -> list[db.LLMModels]:
    return session.query(db.LLMModels).all()


def get_llm_models_by_capability(session: Session, capabilities: list[str]) -> list[db.LLMModels]:

    query = session.query(db.LLMModels).order_by(db.LLMModels.name)

    for capability in capabilities:
        query = query.filter(db.LLMModels.model_capacity.contains([capability]))

    return query.all()


def create_llm_model(
    session: Session, model_name: str, model_description: str, model_capacity: list[str], model_provider: str
) -> db.LLMModels:
    llm_model = db.LLMModels(
        name=model_name,
        description=model_description,
        model_capacity=model_capacity,
        provider=model_provider,
        reference=model_provider + ":" + model_name,
    )
    session.add(llm_model)
    session.commit()
    return llm_model


def delete_llm_model(session: Session, llm_model_id: UUID) -> None:
    session.query(db.LLMModels).filter(db.LLMModels.id == llm_model_id).delete()
    session.commit()


def update_llm_model(session: Session, llm_model: db.LLMModels) -> db.LLMModels:
    existing_llm_model = session.query(db.LLMModels).filter(db.LLMModels.id == llm_model.id).first()
    if not existing_llm_model:
        return None
    if llm_model.name is not None:
        existing_llm_model.name = llm_model.name
    if llm_model.description is not None:
        existing_llm_model.description = llm_model.description
    if llm_model.model_capacity is not None:
        existing_llm_model.model_capacity = llm_model.model_capacity
    if llm_model.provider is not None:
        existing_llm_model.provider = llm_model.provider
    existing_llm_model.reference = llm_model.provider + ":" + llm_model.name
    session.commit()
    session.refresh(existing_llm_model)
    return existing_llm_model
