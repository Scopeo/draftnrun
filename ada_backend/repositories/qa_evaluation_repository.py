import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import LLMJudge
from ada_backend.schemas.qa_evaluation_schema import LLMJudgeCreate, LLMJudgeUpdate

LOGGER = logging.getLogger(__name__)


def create_llm_judge(
    session: Session,
    project_id: UUID,
    judge_data: LLMJudgeCreate,
) -> LLMJudge:
    llm_judge = LLMJudge(
        project_id=project_id,
        name=judge_data.name,
        description=judge_data.description,
        evaluation_type=judge_data.evaluation_type,
        llm_model_reference=judge_data.llm_model_reference,
        prompt_template=judge_data.prompt_template,
        temperature=judge_data.temperature,
    )

    session.add(llm_judge)
    session.commit()
    session.refresh(llm_judge)

    LOGGER.info(f"Created LLM judge {llm_judge.id} for project {project_id}")
    return llm_judge


def get_llm_judges_by_project(
    session: Session,
    project_id: UUID,
) -> List[LLMJudge]:
    return session.query(LLMJudge).filter(LLMJudge.project_id == project_id).order_by(LLMJudge.created_at.desc()).all()


def get_llm_judge_by_id(
    session: Session,
    judge_id: UUID,
) -> Optional[LLMJudge]:
    return session.query(LLMJudge).filter(LLMJudge.id == judge_id).first()


def update_llm_judge(
    session: Session,
    judge_id: UUID,
    judge_data: LLMJudgeUpdate,
    project_id: UUID,
) -> LLMJudge:
    judge = session.query(LLMJudge).filter(LLMJudge.id == judge_id, LLMJudge.project_id == project_id).first()

    if not judge:
        raise ValueError(f"LLM judge {judge_id} not found in project {project_id}")

    if judge_data.name is not None:
        judge.name = judge_data.name
    if judge_data.description is not None:
        judge.description = judge_data.description
    if judge_data.evaluation_type is not None:
        judge.evaluation_type = judge_data.evaluation_type
    if judge_data.llm_model_reference is not None:
        judge.llm_model_reference = judge_data.llm_model_reference
    if judge_data.prompt_template is not None:
        judge.prompt_template = judge_data.prompt_template
    if judge_data.temperature is not None:
        judge.temperature = judge_data.temperature

    session.commit()
    session.refresh(judge)

    LOGGER.info(f"Updated LLM judge {judge_id} for project {project_id}")
    return judge


def delete_llm_judges(
    session: Session,
    judge_ids: List[UUID],
    project_id: UUID,
) -> int:
    deleted_count = (
        session.query(LLMJudge)
        .filter(LLMJudge.id.in_(judge_ids), LLMJudge.project_id == project_id)
        .delete(synchronize_session=False)
    )

    session.commit()

    LOGGER.info(f"Deleted {deleted_count} LLM judges for project {project_id}")
    return deleted_count
