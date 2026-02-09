from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EvaluationType, LLMJudge


def get_llm_judges_by_organization(
    session: Session,
    organization_id: UUID,
) -> List[LLMJudge]:
    return (
        session.query(LLMJudge)
        .filter(LLMJudge.organization_id == organization_id)
        .order_by(LLMJudge.created_at.desc())
        .all()
    )


def get_llm_judge_by_id(
    session: Session,
    judge_id: UUID,
) -> Optional[LLMJudge]:
    return session.query(LLMJudge).filter(LLMJudge.id == judge_id).first()


def get_llm_judge_by_id_and_organization(
    session: Session,
    judge_id: UUID,
    organization_id: UUID,
) -> Optional[LLMJudge]:
    """Get an LLM judge by ID and verify it belongs to the organization."""
    return session.query(LLMJudge).filter(LLMJudge.id == judge_id, LLMJudge.organization_id == organization_id).first()


def create_llm_judge_for_organization(
    session: Session,
    organization_id: UUID,
    name: str,
    description: Optional[str],
    evaluation_type: EvaluationType,
    llm_model_reference: str,
    prompt_template: str,
    temperature: Optional[float] = 1.0,
) -> LLMJudge:
    llm_judge = LLMJudge(
        organization_id=organization_id,
        name=name,
        description=description,
        evaluation_type=evaluation_type,
        llm_model_reference=llm_model_reference,
        prompt_template=prompt_template,
        temperature=temperature,
    )

    session.add(llm_judge)
    session.commit()
    session.refresh(llm_judge)
    return llm_judge


def update_llm_judge_in_organization(
    session: Session,
    judge_id: UUID,
    organization_id: UUID,
    name: Optional[str] = None,
    description: Optional[str] = None,
    evaluation_type: Optional[EvaluationType] = None,
    llm_model_reference: Optional[str] = None,
    prompt_template: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Optional[LLMJudge]:
    judge = get_llm_judge_by_id_and_organization(session, judge_id, organization_id)

    if not judge:
        return None

    if name is not None:
        judge.name = name
    if description is not None:
        judge.description = description
    if evaluation_type is not None:
        judge.evaluation_type = evaluation_type
    if llm_model_reference is not None:
        judge.llm_model_reference = llm_model_reference
    if prompt_template is not None:
        judge.prompt_template = prompt_template
    if temperature is not None:
        judge.temperature = temperature

    session.commit()
    session.refresh(judge)
    return judge


def delete_llm_judges_from_organization(
    session: Session,
    judge_ids: List[UUID],
    organization_id: UUID,
) -> int:
    """Delete LLM judges from an organization."""
    deleted_count = (
        session.query(LLMJudge)
        .filter(LLMJudge.id.in_(judge_ids), LLMJudge.organization_id == organization_id)
        .delete(synchronize_session=False)
    )

    session.commit()
    return deleted_count
