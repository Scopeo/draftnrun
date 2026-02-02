import json
import logging
from uuid import UUID

from deepdiff import DeepDiff
from sqlalchemy.orm import Session

from ada_backend.repositories.qa_evaluation_repository import upsert_judge_evaluation
from ada_backend.repositories.quality_assurance_repository import get_version_output
from ada_backend.schemas.qa_evaluation_schema import (
    BooleanEvaluationResult,
    ErrorEvaluationResult,
    JudgeEvaluationResponse,
)
from ada_backend.services.qa.qa_error import (
    GroundtruthMissingError,
    InvalidFormatError,
    VersionOutputEmptyError,
)

LOGGER = logging.getLogger(__name__)


def _parse_json(value: str, field_name: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise InvalidFormatError(field_name=field_name, expected_format="JSON")


def _compare_json_equality(output: str, groundtruth: str) -> BooleanEvaluationResult:
    output_json = _parse_json(output, "output")
    groundtruth_json = _parse_json(groundtruth, "groundtruth")

    diff = DeepDiff(groundtruth_json, output_json, ignore_order=False, view="tree")

    if not diff:
        return BooleanEvaluationResult(
            type="boolean",
            result=True,
            justification="JSON structures match exactly",
        )
    else:
        return BooleanEvaluationResult(
            type="boolean",
            result=False,
            justification=f"JSON structures differ:\n{diff.pretty()}",
        )


def run_deterministic_evaluation_service(
    session: Session,
    judge_id: UUID,
    version_output_id: UUID,
) -> JudgeEvaluationResponse:
    version_output_id, input_data, groundtruth, output = get_version_output(
        session=session, version_output_id=version_output_id
    )
    try:
        if not output:
            raise VersionOutputEmptyError(version_output_id)

        if not groundtruth:
            raise GroundtruthMissingError()

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
