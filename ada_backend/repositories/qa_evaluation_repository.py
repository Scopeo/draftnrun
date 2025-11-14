import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import LLMJudge
from ada_backend.schemas.qa_evaluation_schema import LLMJudgeCreate

LOGGER = logging.getLogger(__name__)


def create_llm_judge(
    session: Session,
    project_id: UUID,
    judge_data: LLMJudgeCreate,
) -> LLMJudge:
    """Create a new LLM judge for the given project."""
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
    """Return all LLM judges configured for a project."""
    return session.query(LLMJudge).filter(LLMJudge.project_id == project_id).order_by(LLMJudge.created_at.desc()).all()


def get_llm_judge_by_id(
    session: Session,
    judge_id: UUID,
) -> Optional[LLMJudge]:
    """Return a single LLM judge by its identifier."""
    return session.query(LLMJudge).filter(LLMJudge.id == judge_id).first()
