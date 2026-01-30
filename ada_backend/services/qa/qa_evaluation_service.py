import logging
from typing import List, Optional, Tuple
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ada_backend.database.models import EvaluationType, LLMJudge
from ada_backend.repositories.llm_judges_repository import get_llm_judge_by_id
from ada_backend.repositories.qa_evaluation_repository import (
    delete_judge_evaluations,
    get_evaluations_by_version_output,
    upsert_judge_evaluation,
)
from ada_backend.repositories.quality_assurance_repository import get_version_output
from ada_backend.schemas.qa_evaluation_schema import (
    BooleanEvaluationResult,
    ErrorEvaluationResult,
    FreeTextEvaluationResult,
    JudgeEvaluationResponse,
    ScoreEvaluationResult,
)
from ada_backend.services.agent_runner_service import setup_tracing_context
from ada_backend.services.entity_factory import get_llm_provider_and_model
from ada_backend.services.errors import LLMJudgeNotFound
from ada_backend.services.qa.deterministic_evaluators_service import run_deterministic_evaluation_service
from ada_backend.services.qa.qa_error import VersionOutputEmptyError
from engine.components.utils_prompt import fill_prompt_template
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_context import get_trace_manager

LOGGER = logging.getLogger(__name__)

EVALUATION_TYPE_TO_SCHEMA: dict[EvaluationType, type[BaseModel]] = {
    EvaluationType.BOOLEAN: BooleanEvaluationResult,
    EvaluationType.SCORE: ScoreEvaluationResult,
    EvaluationType.FREE_TEXT: FreeTextEvaluationResult,
}


def get_evaluations_by_version_output_service(
    session: Session,
    version_output_id: UUID,
) -> List[JudgeEvaluationResponse]:
    evaluations = get_evaluations_by_version_output(session=session, version_output_id=version_output_id)
    return [JudgeEvaluationResponse.model_validate(eval) for eval in evaluations]


def delete_judge_evaluations_service(
    session: Session,
    evaluation_ids: List[UUID],
) -> None:
    try:
        deleted_count = delete_judge_evaluations(
            session=session,
            evaluation_ids=evaluation_ids,
        )
        LOGGER.info(f"Deleted {deleted_count} judge evaluations")
    except Exception as e:
        LOGGER.error(f"Error in delete_judge_evaluations_service: {str(e)}")
        raise ValueError(f"Failed to delete judge evaluations: {str(e)}") from e


def _setup_judge_evaluation_context(
    session: Session,
    project_id: UUID,
    judge_id: UUID,
    version_output_id: UUID,
) -> Tuple[LLMJudge, CompletionService, Tuple[UUID, dict, Optional[str], str]]:
    setup_tracing_context(session=session, project_id=project_id)

    judge = get_llm_judge_by_id(
        session=session,
        judge_id=judge_id,
    )
    if not judge:
        raise LLMJudgeNotFound(judge_id, project_id)

    version_output_data = get_version_output(
        session=session,
        version_output_id=version_output_id,
    )

    provider, model_name = get_llm_provider_and_model(judge.llm_model_reference)
    completion_service = CompletionService(
        provider=provider,
        model_name=model_name,
        trace_manager=get_trace_manager(),
        temperature=judge.temperature,
    )

    return judge, completion_service, version_output_data


async def _evaluate_single_version_output(
    session: Session,
    judge: LLMJudge,
    judge_id: UUID,
    completion_service: CompletionService,
    version_output_data: Tuple[UUID, dict, Optional[str], str],
) -> JudgeEvaluationResponse:
    version_output_id, input_data, groundtruth, output = version_output_data
    try:
        if not output:
            raise VersionOutputEmptyError(version_output_id)

        formatted_prompt = fill_prompt_template(
            prompt_template=judge.prompt_template,
            component_name=judge.name,
            variables={
                "input": input_data,
                "groundtruth": groundtruth if groundtruth else "",
                "output": output,
            },
        )

        response_format = EVALUATION_TYPE_TO_SCHEMA.get(judge.evaluation_type)

        evaluation_result = await completion_service.constrained_complete_with_pydantic_async(
            messages=formatted_prompt,
            response_format=response_format,
        )

    except Exception as e:
        error_msg = str(e)
        evaluation_result = ErrorEvaluationResult(justification=error_msg)
        LOGGER.error(f"Error evaluating version_output {version_output_id} with judge {judge_id}: {error_msg}")

    evaluation = upsert_judge_evaluation(
        session=session,
        judge_id=judge_id,
        version_output_id=version_output_id,
        evaluation_result=evaluation_result.model_dump(exclude_none=True),
    )

    return JudgeEvaluationResponse.model_validate(evaluation)


async def run_judge_evaluation_service(
    session: Session,
    project_id: UUID,
    judge_id: UUID,
    version_output_id: UUID,
) -> JudgeEvaluationResponse:
    try:
        judge = get_llm_judge_by_id(session=session, judge_id=judge_id)
        if not judge:
            raise LLMJudgeNotFound(judge_id, project_id)

        # TODO: Deterministic evaluations will have their own dedicated service and endpoint
        # - The function as it was before was EXACTLY what is in the "else" :
        # - To revert to original function, delete everything that is not in the "else" or the "except"
        if judge.evaluation_type == EvaluationType.JSON_EQUALITY:
            return run_deterministic_evaluation_service(
                session=session,
                judge_id=judge_id,
                version_output_id=version_output_id,
            )
        else:
            judge, completion_service, version_output_data = _setup_judge_evaluation_context(
                session=session,
                project_id=project_id,
                judge_id=judge_id,
                version_output_id=version_output_id,
            )

            result = await _evaluate_single_version_output(
                session=session,
                judge=judge,
                judge_id=judge_id,
                completion_service=completion_service,
                version_output_data=version_output_data,
            )

            LOGGER.info(f"Judge evaluation completed for judge {judge_id} and version_output {version_output_id}")

            return result
    except Exception as e:
        LOGGER.error(f"Error in run_judge_evaluation_service: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to run judge evaluation: {str(e)}") from e
