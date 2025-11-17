import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.qa_evaluation_repository import (
    create_llm_judge,
    get_llm_judges_by_project,
    update_llm_judge,
    delete_llm_judges,
)
from ada_backend.schemas.qa_evaluation_schema import (
    LLMJudgeCreate,
    LLMJudgeResponse,
    LLMJudgeListResponse,
    LLMJudgeUpdate,
    LLMJudgeDeleteList,
)
from ada_backend.services.errors import LLMJudgeNotFound

LOGGER = logging.getLogger(__name__)


def create_llm_judge_service(
    session: Session,
    project_id: UUID,
    judge_data: LLMJudgeCreate,
) -> LLMJudgeResponse:
    try:
        llm_judge = create_llm_judge(
            session=session,
            project_id=project_id,
            name=judge_data.name,
            description=judge_data.description,
            evaluation_type=judge_data.evaluation_type,
            llm_model_reference=judge_data.llm_model_reference,
            prompt_template=judge_data.prompt_template,
            temperature=judge_data.temperature,
        )
        LOGGER.info(f"Created LLM judge {llm_judge.id} for project {project_id}")
        return LLMJudgeResponse.model_validate(llm_judge)
    except Exception as e:
        LOGGER.error(f"Error in create_llm_judge_service for project {project_id}: {str(e)}")
        raise ValueError(f"Failed to create LLM judge: {str(e)}") from e


def get_llm_judges_by_project_service(
    session: Session,
    project_id: UUID,
) -> LLMJudgeListResponse:
    try:
        judges = get_llm_judges_by_project(session=session, project_id=project_id)
        return LLMJudgeListResponse(judges=[LLMJudgeResponse.model_validate(judge) for judge in judges])
    except Exception as e:
        LOGGER.error(f"Error in get_llm_judges_by_project_service for project {project_id}: {str(e)}")
        raise ValueError(f"Failed to list LLM judges: {str(e)}") from e


def update_llm_judge_service(
    session: Session,
    project_id: UUID,
    judge_id: UUID,
    judge_data: LLMJudgeUpdate,
) -> LLMJudgeResponse:
    try:
        updated_judge = update_llm_judge(
            session=session,
            judge_id=judge_id,
            project_id=project_id,
            name=judge_data.name,
            description=judge_data.description,
            evaluation_type=judge_data.evaluation_type,
            llm_model_reference=judge_data.llm_model_reference,
            prompt_template=judge_data.prompt_template,
            temperature=judge_data.temperature,
        )
        if not updated_judge:
            raise LLMJudgeNotFound(judge_id=judge_id, project_id=project_id)
        LOGGER.info(f"Updated LLM judge {judge_id} for project {project_id}")
        return LLMJudgeResponse.model_validate(updated_judge)
    except Exception as e:
        LOGGER.error(f"Error in update_llm_judge_service for judge {judge_id}: {str(e)}")
        raise ValueError(f"Failed to update LLM judge: {str(e)}") from e


def delete_llm_judges_service(
    session: Session,
    project_id: UUID,
    delete_data: LLMJudgeDeleteList,
) -> None:
    try:
        deleted_count = delete_llm_judges(
            session=session,
            judge_ids=delete_data.judge_ids,
            project_id=project_id,
        )
        LOGGER.info(f"Deleted {deleted_count} LLM judges for project {project_id}")
    except Exception as e:
        LOGGER.error(f"Error in delete_llm_judges_service for project {project_id}: {str(e)}")
        raise ValueError(f"Failed to delete LLM judges: {str(e)}") from e
