import logging
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.qa_evaluation_repository import (
    create_llm_judge,
    get_llm_judges_by_project,
    update_llm_judge,
    delete_llm_judges,
    create_judge_evaluation,
    get_judge_evaluations_by_judge,
    get_judge_evaluations_by_version_output,
    delete_judge_evaluations,
    get_version_outputs_by_ids,
)
from ada_backend.schemas.qa_evaluation_schema import (
    LLMJudgeCreate,
    LLMJudgeResponse,
    LLMJudgeUpdate,
    JudgeEvaluationCreate,
    JudgeEvaluationResponse,
    JudgeEvaluationRunResponse,
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
) -> List[LLMJudgeResponse]:
    try:
        judges = get_llm_judges_by_project(session=session, project_id=project_id)
        return [LLMJudgeResponse.model_validate(judge) for judge in judges]
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


def create_judge_evaluation_service(
    session: Session,
    project_id: UUID,
    judge_id: UUID,
    evaluation_data: JudgeEvaluationCreate,
) -> JudgeEvaluationResponse:
    try:
        evaluation = create_judge_evaluation(
            session=session,
            judge_id=judge_id,
            version_output_id=evaluation_data.version_output_id,
            evaluation_result=evaluation_data.evaluation_result,
            project_id=project_id,
            raw_llm_response=evaluation_data.raw_llm_response,
        )

        if not evaluation:
            raise ValueError("Version output not found or evaluation already exists")

        LOGGER.info(f"Created judge evaluation {evaluation.id}")
        return JudgeEvaluationResponse.model_validate(evaluation)
    except LLMJudgeNotFound:
        raise
    except Exception as e:
        LOGGER.error(f"Error in create_judge_evaluation_service: {str(e)}")
        raise ValueError(f"Failed to create judge evaluation: {str(e)}") from e


def get_judge_evaluations_by_judge_service(
    session: Session,
    judge_id: UUID,
) -> List[JudgeEvaluationResponse]:
    try:
        evaluations = get_judge_evaluations_by_judge(session=session, judge_id=judge_id)
        return [JudgeEvaluationResponse.model_validate(eval) for eval in evaluations]
    except Exception as e:
        LOGGER.error(f"Error in get_judge_evaluations_by_judge_service: {str(e)}")
        raise ValueError(f"Failed to get judge evaluations: {str(e)}") from e


def get_judge_evaluations_by_version_output_service(
    session: Session,
    version_output_id: UUID,
) -> List[JudgeEvaluationResponse]:
    try:
        evaluations = get_judge_evaluations_by_version_output(session=session, version_output_id=version_output_id)
        return [JudgeEvaluationResponse.model_validate(eval) for eval in evaluations]
    except Exception as e:
        LOGGER.error(f"Error in get_judge_evaluations_by_version_output_service: {str(e)}")
        raise ValueError(f"Failed to get judge evaluations: {str(e)}") from e


def delete_judge_evaluations_service(
    session: Session,
    project_id: UUID,
    evaluation_ids: List[UUID],
) -> None:
    try:
        deleted_count = delete_judge_evaluations(
            session=session,
            evaluation_ids=evaluation_ids,
            project_id=project_id,
        )
        LOGGER.info(f"Deleted {deleted_count} judge evaluations for project {project_id}")
    except Exception as e:
        LOGGER.error(f"Error in delete_judge_evaluations_service: {str(e)}")
        raise ValueError(f"Failed to delete judge evaluations: {str(e)}") from e


async def run_judge_evaluation_service(
    session: Session,
    project_id: UUID,
    judge_id: UUID,
    version_output_ids: List[UUID],
) -> JudgeEvaluationRunResponse:
    # TODO: A implémenter
    try:
        version_outputs_data = get_version_outputs_by_ids(session=session, version_output_ids=version_output_ids)

        # TODO: Pour chaque version_output, appeler le LLM et créer l'évaluation
        return JudgeEvaluationRunResponse(results=[], sucess_rate=0.0)
    except Exception as e:
        LOGGER.error(f"Error in run_judge_evaluation_service: {str(e)}")
        raise ValueError(f"Failed to run judge evaluation: {str(e)}") from e
