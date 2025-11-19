import logging
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import LLMJudge, JudgeEvaluation, VersionOutput, InputGroundtruth, EvaluationType
from ada_backend.services.errors import LLMJudgeNotFound

LOGGER = logging.getLogger(__name__)


def create_llm_judge(
    session: Session,
    project_id: UUID,
    name: str,
    description: Optional[str],
    evaluation_type: EvaluationType,
    llm_model_reference: str,
    prompt_template: str,
    temperature: Optional[float] = 1.0,
) -> LLMJudge:
    llm_judge = LLMJudge(
        project_id=project_id,
        name=name,
        description=description,
        evaluation_type=evaluation_type,
        llm_model_reference=llm_model_reference,
        prompt_template=prompt_template,
        temperature=temperature,
    )

    session.add(llm_judge)
    session.commit()
    session.refresh(llm_judge)
    return llm_judge


def get_llm_judges_by_project(
    session: Session,
    project_id: UUID,
) -> List[LLMJudge]:
    return session.query(LLMJudge).filter(LLMJudge.project_id == project_id).order_by(LLMJudge.created_at.desc()).all()


def update_llm_judge(
    session: Session,
    judge_id: UUID,
    project_id: UUID,
    name: Optional[str] = None,
    description: Optional[str] = None,
    evaluation_type: Optional[EvaluationType] = None,
    llm_model_reference: Optional[str] = None,
    prompt_template: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Optional[LLMJudge]:
    judge = session.query(LLMJudge).filter(LLMJudge.id == judge_id, LLMJudge.project_id == project_id).first()

    if not judge:
        return None

    if name is not None:
        judge.name = name
    if description is not None:
        judge.description = description
    if evaluation_type is not None:
        judge.evaluation_type = evaluation_type
    if llm_model_reference is not None:
        judge.llm_model_reference = llm_model_reference
    if prompt_template is not None:
        judge.prompt_template = prompt_template
    if temperature is not None:
        judge.temperature = temperature

    session.commit()
    session.refresh(judge)
    return judge


def delete_llm_judges(
    session: Session,
    judge_ids: List[UUID],
    project_id: UUID,
) -> int:
    deleted_count = (
        session.query(LLMJudge)
        .filter(LLMJudge.id.in_(judge_ids), LLMJudge.project_id == project_id)
        .delete(synchronize_session=False)
    )

    session.commit()
    return deleted_count


def create_judge_evaluation(
    session: Session,
    judge_id: UUID,
    version_output_id: UUID,
    evaluation_result: dict,
    project_id: UUID,
    raw_llm_response: Optional[str] = None,
) -> Optional[JudgeEvaluation]:
    judge = session.query(LLMJudge).filter(LLMJudge.id == judge_id, LLMJudge.project_id == project_id).first()
    if not judge:
        raise LLMJudgeNotFound(judge_id, project_id)

    version_output = session.query(VersionOutput).filter(VersionOutput.id == version_output_id).first()
    if not version_output:
        return None

    existing = get_judge_evaluation_by_judge_and_version_output(session, judge_id, version_output_id)
    if existing:
        return None

    evaluation = JudgeEvaluation(
        judge_id=judge_id,
        version_output_id=version_output_id,
        evaluation_result=evaluation_result,
        raw_llm_response=raw_llm_response,
    )

    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)
    LOGGER.info(f"Created judge evaluation for judge {judge_id} and version_output {version_output_id}")
    return evaluation


def get_judge_evaluations_by_judge(
    session: Session,
    judge_id: UUID,
) -> List[JudgeEvaluation]:
    return (
        session.query(JudgeEvaluation)
        .filter(JudgeEvaluation.judge_id == judge_id)
        .order_by(JudgeEvaluation.created_at.desc())
        .all()
    )


def get_judge_evaluations_by_version_output(
    session: Session,
    version_output_id: UUID,
) -> List[JudgeEvaluation]:
    return (
        session.query(JudgeEvaluation)
        .filter(JudgeEvaluation.version_output_id == version_output_id)
        .order_by(JudgeEvaluation.created_at.desc())
        .all()
    )


def get_judge_evaluation_by_id(
    session: Session,
    evaluation_id: UUID,
) -> Optional[JudgeEvaluation]:
    return session.query(JudgeEvaluation).filter(JudgeEvaluation.id == evaluation_id).first()


def delete_judge_evaluations(
    session: Session,
    evaluation_ids: List[UUID],
    project_id: UUID,
) -> int:
    deleted_count = (
        session.query(JudgeEvaluation)
        .join(LLMJudge, JudgeEvaluation.judge_id == LLMJudge.id)
        .filter(
            JudgeEvaluation.id.in_(evaluation_ids),
            LLMJudge.project_id == project_id,
        )
        .delete(synchronize_session=False)
    )

    session.commit()
    return deleted_count


def get_judge_evaluation_by_judge_and_version_output(
    session: Session,
    judge_id: UUID,
    version_output_id: UUID,
) -> Optional[JudgeEvaluation]:
    return (
        session.query(JudgeEvaluation)
        .filter(JudgeEvaluation.judge_id == judge_id, JudgeEvaluation.version_output_id == version_output_id)
        .first()
    )


def upsert_judge_evaluation(
    session: Session,
    judge_id: UUID,
    version_output_id: UUID,
    evaluation_result: dict,
    raw_llm_response: Optional[str] = None,
) -> JudgeEvaluation:
    existing = get_judge_evaluation_by_judge_and_version_output(session, judge_id, version_output_id)
    if existing:
        existing.evaluation_result = evaluation_result
        existing.raw_llm_response = raw_llm_response
        session.commit()
        session.refresh(existing)
        LOGGER.info(f"Updated judge evaluation for judge {judge_id} and version_output {version_output_id}")
        return existing

    evaluation = JudgeEvaluation(
        judge_id=judge_id,
        version_output_id=version_output_id,
        evaluation_result=evaluation_result,
        raw_llm_response=raw_llm_response,
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)
    LOGGER.info(f"Created judge evaluation for judge {judge_id} and version_output {version_output_id}")
    return evaluation


def get_version_outputs_by_ids(
    session: Session,
    version_output_ids: List[UUID],
) -> List[Tuple[UUID, dict, Optional[str], str]]:
    """Get version outputs with input and groundtruth data by their IDs.

    Args:
        session: SQLAlchemy session
        version_output_ids: List of version output IDs

    Returns:
        List of tuples (version_output_id, input, groundtruth, output)
    """
    results = (
        session.query(
            VersionOutput.id,
            InputGroundtruth.input,
            InputGroundtruth.groundtruth,
            VersionOutput.output,
        )
        .join(InputGroundtruth, InputGroundtruth.id == VersionOutput.input_id)
        .filter(VersionOutput.id.in_(version_output_ids))
        .all()
    )

    return results
