import json
import logging
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EvaluationType, LLMJudge
from ada_backend.repositories.qa_evaluation_repository import upsert_judge_evaluation
from ada_backend.schemas.qa_evaluation_schema import (
    BooleanEvaluationResult,
    ErrorEvaluationResult,
    JudgeEvaluationResponse,
)
from ada_backend.services.qa.qa_error import VersionOutputEmptyError

LOGGER = logging.getLogger(__name__)


def _compare_json_equality(output: str, groundtruth: Optional[str]) -> BooleanEvaluationResult:
    if not groundtruth:
        return BooleanEvaluationResult(
            type="boolean",
            result=False,
            justification="No groundtruth provided",
        )

    try:
        output_json = json.loads(output)
    except json.JSONDecodeError:
        return BooleanEvaluationResult(
            type="boolean",
            result=False,
            justification="Invalid JSON format in output",
        )

    try:
        groundtruth_json = json.loads(groundtruth)
    except json.JSONDecodeError:
        return BooleanEvaluationResult(
            type="boolean",
            result=False,
            justification="Invalid JSON format in groundtruth",
        )

    if output_json == groundtruth_json:
        return BooleanEvaluationResult(
            type="boolean",
            result=True,
            justification="JSON structures match exactly",
        )
    else:
        return BooleanEvaluationResult(
            type="boolean",
            result=False,
            justification="JSON structures differ",
        )


def run_deterministic_evaluation_service(
    session: Session,
    judge: LLMJudge,
    judge_id: UUID,
    version_output_data: Tuple[UUID, dict, Optional[str], str],
) -> JudgeEvaluationResponse:
    version_output_id, input_data, groundtruth, output = version_output_data
    try:
        if not output:
            raise VersionOutputEmptyError(version_output_id)

        if judge.evaluation_type == EvaluationType.JSON_EQUALITY:
            evaluation_result = _compare_json_equality(output, groundtruth)
        else:
            raise ValueError(f"Unsupported deterministic evaluation type: {judge.evaluation_type}")

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
