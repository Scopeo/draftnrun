import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EvaluationType, LLMJudge
from ada_backend.repositories.qa_evaluation_repository import upsert_judge_evaluation
from ada_backend.repositories.quality_assurance_repository import get_version_output
from ada_backend.schemas.qa_evaluation_schema import (
    BooleanEvaluationResult,
    ErrorEvaluationResult,
    JudgeEvaluationResponse,
)
from ada_backend.services.qa.qa_error import (
    GroundtruthMissingError,
    InvalidGroundtruthFormatError,
    InvalidOutputFormatError,
    VersionOutputEmptyError,
)

LOGGER = logging.getLogger(__name__)


def _parse_json_pair(output: str, groundtruth: Optional[str]):
    if not groundtruth:
        raise GroundtruthMissingError()

    try:
        output_json = json.loads(output)
    except json.JSONDecodeError as e:
        raise InvalidOutputFormatError(expected_format="JSON")

    try:
        groundtruth_json = json.loads(groundtruth)
    except json.JSONDecodeError as e:
        raise InvalidGroundtruthFormatError(expected_format="JSON")

    return output_json, groundtruth_json


def _compare_json_equality(output: str, groundtruth: Optional[str]):
    output_json, groundtruth_json = _parse_json_pair(output, groundtruth)

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
    version_output_id: UUID,
) -> JudgeEvaluationResponse:
    version_output_data = get_version_output(session=session, version_output_id=version_output_id)
    version_output_id, input_data, groundtruth, output = version_output_data
    try:
        if not output:
            raise VersionOutputEmptyError(version_output_id)

        evaluation_result = _compare_json_equality(output, groundtruth)

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
