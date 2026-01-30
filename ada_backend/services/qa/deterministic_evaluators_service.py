import json
import logging
from typing import Tuple
from uuid import UUID

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


def _parse_json_pair(output: str, groundtruth: str) -> Tuple[dict, dict]:
    try:
        output_json = json.loads(output)
    except json.JSONDecodeError:
        raise InvalidFormatError(field_name="output", expected_format="JSON")

    try:
        groundtruth_json = json.loads(groundtruth)
    except json.JSONDecodeError:
        raise InvalidFormatError(field_name="groundtruth", expected_format="JSON")

    return output_json, groundtruth_json


def _get_diff_details(output_json: dict, groundtruth_json: dict) -> list[str]:
    output_keys = set(output_json.keys())
    groundtruth_keys = set(groundtruth_json.keys())

    missing_keys = groundtruth_keys - output_keys
    extra_keys = output_keys - groundtruth_keys
    common_keys = output_keys & groundtruth_keys

    diff_keys = [key for key in common_keys if output_json[key] != groundtruth_json[key]]

    details = []
    if missing_keys:
        details.append(f"Missing keys: {sorted(missing_keys)}")
    if extra_keys:
        details.append(f"Extra keys: {sorted(extra_keys)}")
    if diff_keys:
        details.append(f"{len(diff_keys)} key(s) with different values")

    return details


def _compare_json_equality(output: str, groundtruth: str) -> BooleanEvaluationResult:
    output_json, groundtruth_json = _parse_json_pair(output, groundtruth)

    details = _get_diff_details(output_json, groundtruth_json)

    if not details:
        return BooleanEvaluationResult(
            type="boolean",
            result=True,
            justification="JSON structures match exactly",
        )
    else:
        return BooleanEvaluationResult(
            type="boolean",
            result=False,
            justification=f"JSON structures differ:\n{'\n'.join(details)}",
        )


def run_deterministic_evaluation_service(
    session: Session,
    judge_id: UUID,
    version_output_id: UUID,
) -> JudgeEvaluationResponse:
    version_output_data = get_version_output(session=session, version_output_id=version_output_id)
    version_output_id, input_data, groundtruth, output = version_output_data
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
