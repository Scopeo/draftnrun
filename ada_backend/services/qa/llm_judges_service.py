import logging
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EvaluationType
from ada_backend.repositories.llm_judges_repository import (
    create_llm_judge,
    delete_llm_judges,
    get_llm_judge_by_id,
    get_llm_judges_by_organization,
    get_llm_judges_by_project,
    get_valid_project_ids_for_organization,
    set_judge_project_associations,
    update_llm_judge,
)
from ada_backend.schemas.llm_judges_schema import (
    LLMJudgeCreate,
    LLMJudgeResponse,
    LLMJudgeTemplate,
    LLMJudgeUpdate,
)
from ada_backend.services.errors import LLMJudgeNotFound, LLMJudgeOperationError, ProjectNotFound
from ada_backend.services.qa.utils import (
    DEFAULT_BOOLEAN_PROMPT,
    DEFAULT_FREE_TEXT_PROMPT,
    DEFAULT_JSON_EQUALITY_PROMPT,
    DEFAULT_SCORE_PROMPT,
)

LOGGER = logging.getLogger(__name__)


def _judge_to_response(judge) -> LLMJudgeResponse:
    return LLMJudgeResponse(
        id=judge.id,
        organization_id=judge.organization_id,
        name=judge.name,
        description=judge.description,
        evaluation_type=judge.evaluation_type,
        llm_model_reference=judge.llm_model_reference,
        prompt_template=judge.prompt_template,
        temperature=judge.temperature,
        project_ids=[assoc.project_id for assoc in judge.project_associations],
        created_at=judge.created_at,
        updated_at=judge.updated_at,
    )


def get_llm_judges_by_project_service(
    session: Session,
    project_id: UUID,
) -> List[LLMJudgeResponse]:
    try:
        judges = get_llm_judges_by_project(session=session, project_id=project_id)
        return [_judge_to_response(judge) for judge in judges]
    except Exception as e:
        LOGGER.error(f"Error in get_llm_judges_by_project_service for project {project_id}: {str(e)}")
        raise LLMJudgeOperationError(f"Failed to list LLM judges: {str(e)}") from e


def get_llm_judges_by_organization_service(
    session: Session,
    organization_id: UUID,
) -> List[LLMJudgeResponse]:
    try:
        judges = get_llm_judges_by_organization(session=session, organization_id=organization_id)
        return [_judge_to_response(judge) for judge in judges]
    except Exception as e:
        LOGGER.error(f"Error in get_llm_judges_by_organization_service for org {organization_id}: {str(e)}")
        raise LLMJudgeOperationError(f"Failed to list LLM judges: {str(e)}") from e


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
    organization_id: UUID,
    judge_data: LLMJudgeCreate,
) -> LLMJudgeResponse:
    try:
        llm_judge = create_llm_judge(
            session=session,
            organization_id=organization_id,
            name=judge_data.name,
            description=judge_data.description,
            evaluation_type=judge_data.evaluation_type,
            llm_model_reference=judge_data.llm_model_reference,
            prompt_template=judge_data.prompt_template,
            temperature=judge_data.temperature,
        )
        LOGGER.info(f"Created LLM judge {llm_judge.id} for organization {organization_id}")
        return _judge_to_response(llm_judge)
    except Exception as e:
        raise LLMJudgeOperationError(f"Failed to create LLM judge: {str(e)}") from e
        LOGGER.error(f"Error in create_llm_judge_service for organization {organization_id}: {str(e)}")
        raise LLMJudgeOperationError(f"Failed to create LLM judge: {str(e)}") from e


def update_llm_judge_service(
    session: Session,
    organization_id: UUID,
    judge_id: UUID,
    judge_data: LLMJudgeUpdate,
) -> LLMJudgeResponse:
    try:
        updated_judge = update_llm_judge(
            session=session,
            judge_id=judge_id,
            organization_id=organization_id,
            name=judge_data.name,
            description=judge_data.description,
            evaluation_type=judge_data.evaluation_type,
            llm_model_reference=judge_data.llm_model_reference,
            prompt_template=judge_data.prompt_template,
            temperature=judge_data.temperature,
        )
        if not updated_judge:
            raise LLMJudgeNotFound(judge_id=judge_id, organization_id=organization_id)
        LOGGER.info(f"Updated LLM judge {judge_id} for organization {organization_id}")
        return _judge_to_response(updated_judge)
    except LLMJudgeNotFound:
        raise
    except Exception as e:
        LOGGER.error(f"Error in update_llm_judge_service for judge {judge_id}: {str(e)}")
        raise LLMJudgeOperationError(f"Failed to update LLM judge: {str(e)}") from e


def delete_llm_judges_service(
    session: Session,
    organization_id: UUID,
    judge_ids: List[UUID],
) -> None:
    try:
        deleted_count = delete_llm_judges(
            session=session,
            judge_ids=judge_ids,
            organization_id=organization_id,
        )
        LOGGER.info(f"Deleted {deleted_count} LLM judges for organization {organization_id}")
    except Exception as e:
        LOGGER.error(f"Error in delete_llm_judges_service for organization {organization_id}: {str(e)}")
        raise LLMJudgeOperationError(f"Failed to delete LLM judges: {str(e)}") from e


def set_judge_projects_service(
    session: Session,
    organization_id: UUID,
    judge_id: UUID,
    project_ids: List[UUID],
) -> LLMJudgeResponse:
    judge = get_llm_judge_by_id(session, judge_id, organization_id=organization_id)
    if not judge:
        raise LLMJudgeNotFound(judge_id=judge_id, organization_id=organization_id)

    if project_ids:
        valid_ids = get_valid_project_ids_for_organization(session, project_ids, organization_id)
        invalid_ids = set(project_ids) - valid_ids
        if invalid_ids:
            raise ProjectNotFound(project_id=next(iter(invalid_ids)))

    set_judge_project_associations(session, judge_id, project_ids)
    session.refresh(judge)
    return _judge_to_response(judge)
