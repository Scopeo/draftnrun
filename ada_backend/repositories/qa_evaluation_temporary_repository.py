from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import JudgeEvaluation


def get_evaluations_by_version_output(
    session: Session,
    version_output_id: UUID,
) -> List[JudgeEvaluation]:
    return (
        session.query(JudgeEvaluation)
        .filter(JudgeEvaluation.version_output_id == version_output_id)
        .order_by(JudgeEvaluation.created_at.desc())
        .all()
    )


def get_evaluation_by_judge_and_version_output(
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
) -> JudgeEvaluation:
    existing = get_evaluation_by_judge_and_version_output(session, judge_id, version_output_id)
    if existing:
        existing.evaluation_result = evaluation_result
        session.commit()
        session.refresh(existing)
        return existing

    evaluation = JudgeEvaluation(
        judge_id=judge_id,
        version_output_id=version_output_id,
        evaluation_result=evaluation_result,
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)
    return evaluation


def delete_judge_evaluations(
    session: Session,
    evaluation_ids: List[UUID],
) -> int:
    deleted_count = (
        session.query(JudgeEvaluation).filter(JudgeEvaluation.id.in_(evaluation_ids)).delete(synchronize_session=False)
    )

    session.commit()
    return deleted_count
