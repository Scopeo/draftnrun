import logging
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EvaluationType
from ada_backend.repositories.llm_judges_repository import (
    create_llm_judge,
    delete_llm_judges,
    get_llm_judges_by_project,
    update_llm_judge,
)
from ada_backend.schemas.llm_judges_schema import (
    LLMJudgeCreate,
    LLMJudgeResponse,
    LLMJudgeTemplate,
    LLMJudgeUpdate,
)
from ada_backend.services.errors import LLMJudgeNotFound
from ada_backend.services.qa.utils import (
    DEFAULT_BOOLEAN_PROMPT,
    DEFAULT_FREE_TEXT_PROMPT,
    DEFAULT_JSON_EQUALITY_PROMPT,
    DEFAULT_SCORE_PROMPT,
)

LOGGER = logging.getLogger(__name__)


def get_llm_judges_by_project_service(
    session: Session,
    project_id: UUID,
) -> List[LLMJudgeResponse]:
    try:
        judges = get_llm_judges_by_project(session=session, project_id=project_id)
        return [LLMJudgeResponse.model_validate(judge) for judge in judges]
    except Exception as e:
        LOGGER.error(f"Error in get_llm_judges_by_project_service for project {project_id}: {str(e)}")
        raise ValueError(f"Failed to list LLM judges: {str(e)}") from e


def get_llm_judge_defaults_service(
    evaluation_type: EvaluationType,
) -> LLMJudgeTemplate:
    if evaluation_type == EvaluationType.BOOLEAN:
        prompt_template = DEFAULT_BOOLEAN_PROMPT
    elif evaluation_type == EvaluationType.SCORE:
        prompt_template = DEFAULT_SCORE_PROMPT
    elif evaluation_type == EvaluationType.FREE_TEXT:
        prompt_template = DEFAULT_FREE_TEXT_PROMPT
    elif evaluation_type == EvaluationType.JSON_EQUALITY:
        prompt_template = DEFAULT_JSON_EQUALITY_PROMPT

    return LLMJudgeTemplate(
        evaluation_type=evaluation_type,
        llm_model_reference=None,
        prompt_template=prompt_template,
        temperature=None,
    )


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
    except LLMJudgeNotFound:
        raise
    except Exception as e:
        LOGGER.error(f"Error in update_llm_judge_service for judge {judge_id}: {str(e)}")
        raise ValueError(f"Failed to update LLM judge: {str(e)}") from e


def delete_llm_judges_service(
    session: Session,
    project_id: UUID,
    judge_ids: List[UUID],
) -> None:
    try:
        deleted_count = delete_llm_judges(
            session=session,
            judge_ids=judge_ids,
            project_id=project_id,
        )
        LOGGER.info(f"Deleted {deleted_count} LLM judges for project {project_id}")
    except Exception as e:
        LOGGER.error(f"Error in delete_llm_judges_service for project {project_id}: {str(e)}")
        raise ValueError(f"Failed to delete LLM judges: {str(e)}") from e
