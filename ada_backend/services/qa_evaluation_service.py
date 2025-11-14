import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.qa_evaluation_repository import (
    create_llm_judge,
    get_llm_judges_by_project,
)
from ada_backend.schemas.qa_evaluation_schema import (
    LLMJudgeCreate,
    LLMJudgeResponse,
    LLMJudgeListResponse,
)

LOGGER = logging.getLogger(__name__)


def create_llm_judge_service(
    session: Session,
    project_id: UUID,
    judge_data: LLMJudgeCreate,
) -> LLMJudgeResponse:
    """Create an LLM judge for a project."""
    try:
        llm_judge = create_llm_judge(session=session, project_id=project_id, judge_data=judge_data)
        LOGGER.info(f"Created LLM judge {llm_judge.id} for project {project_id}")
        return LLMJudgeResponse.model_validate(llm_judge)
    except Exception as e:
        LOGGER.error(f"Error in create_llm_judge_service for project {project_id}: {str(e)}")
        raise ValueError(f"Failed to create LLM judge: {str(e)}") from e


def get_llm_judges_by_project_service(
    session: Session,
    project_id: UUID,
) -> LLMJudgeListResponse:
    """Return the list of LLM judges configured for a project."""
    try:
        judges = get_llm_judges_by_project(session=session, project_id=project_id)
        return LLMJudgeListResponse(judges=[LLMJudgeResponse.model_validate(judge) for judge in judges])
    except Exception as e:
        LOGGER.error(f"Error in get_llm_judges_by_project_service for project {project_id}: {str(e)}")
        raise ValueError(f"Failed to list LLM judges: {str(e)}") from e
