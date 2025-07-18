import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func

from engine.evaluations.models import QuestionsAnswers
from ada_backend.schemas.question_answer_schema import QuestionAnswerCreate

LOGGER = logging.getLogger(__name__)


def get_questions_answers_by_organization(
    session: Session,
    organization_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[QuestionsAnswers]:
    """Get all question-answer entries for an organization with pagination."""
    return (
        session.query(QuestionsAnswers)
        .filter(QuestionsAnswers.organization_id == organization_id)
        .order_by(QuestionsAnswers.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_questions_answers_by_organization_and_project(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[QuestionsAnswers]:
    """Get all question-answer entries for an organization and project with pagination."""
    return (
        session.query(QuestionsAnswers)
        .filter(
            QuestionsAnswers.organization_id == organization_id,
            QuestionsAnswers.project_id == project_id,
        )
        .order_by(QuestionsAnswers.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_questions_answers_count_by_organization(
    session: Session,
    organization_id: UUID,
) -> int:
    """Get total count of question-answer entries for an organization."""
    return (
        session.query(func.count(QuestionsAnswers.id))
        .filter(QuestionsAnswers.organization_id == organization_id)
        .scalar()
    )


def get_questions_answers_count_by_organization_and_project(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
) -> int:
    """Get total count of question-answer entries for an organization and project."""
    return (
        session.query(func.count(QuestionsAnswers.id))
        .filter(
            QuestionsAnswers.organization_id == organization_id,
            QuestionsAnswers.project_id == project_id,
        )
        .scalar()
    )


def get_questions_answers_with_pagination(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
    page: int = 1,
    size: int = 100,
) -> tuple[List[QuestionsAnswers], int]:
    """Get question-answer entries with pagination and total count."""
    # Calculate skip
    skip = (page - 1) * size

    # Get total count
    total = get_questions_answers_count_by_organization_and_project(session, organization_id, project_id)

    # Get paginated results
    questions_answers = get_questions_answers_by_organization_and_project(
        session, organization_id, project_id, skip, size
    )

    return questions_answers, total


def get_question_answer_by_id(
    session: Session,
    question_answer_id: UUID,
    organization_id: UUID,
    project_id: UUID,
) -> QuestionsAnswers | None:
    """Get a specific question-answer entry by ID, organization, and project."""
    return (
        session.query(QuestionsAnswers)
        .filter(
            QuestionsAnswers.id == question_answer_id,
            QuestionsAnswers.organization_id == organization_id,
            QuestionsAnswers.project_id == project_id,
        )
        .first()
    )


def create_question_answer(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
    question: str,
    groundtruth: str,
) -> QuestionsAnswers:
    """Create a new question-answer entry."""
    question_answer = QuestionsAnswers(
        organization_id=organization_id,
        project_id=project_id,
        question=question,
        groundtruth=groundtruth,
    )
    session.add(question_answer)
    session.commit()
    session.refresh(question_answer)
    return question_answer


def create_questions_answers(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
    questions_answers_data: List[QuestionAnswerCreate],
) -> List[QuestionsAnswers]:
    """Create multiple question-answer entries."""
    question_answers = []
    for qa_data in questions_answers_data:
        question_answer = QuestionsAnswers(
            organization_id=organization_id,
            project_id=project_id,
            question=qa_data.question,
            groundtruth=qa_data.groundtruth,
        )
        question_answers.append(question_answer)

    session.add_all(question_answers)
    session.commit()

    # Refresh all created objects to get their IDs
    for qa in question_answers:
        session.refresh(qa)

    return question_answers


def update_question_answer(
    session: Session,
    question_answer_id: UUID,
    organization_id: UUID,
    project_id: UUID,
    question: Optional[str] = None,
    groundtruth: Optional[str] = None,
) -> QuestionsAnswers | None:
    """Update an existing question-answer entry."""
    question_answer = get_question_answer_by_id(session, question_answer_id, organization_id, project_id)
    if not question_answer:
        return None

    if question is not None:
        question_answer.question = question
    if groundtruth is not None:
        question_answer.groundtruth = groundtruth

    session.commit()
    session.refresh(question_answer)
    return question_answer


def delete_question_answer(
    session: Session,
    question_answer_id: UUID,
    organization_id: UUID,
    project_id: UUID,
) -> bool:
    """Delete a question-answer entry."""
    question_answer = get_question_answer_by_id(session, question_answer_id, organization_id, project_id)
    if not question_answer:
        return False

    session.delete(question_answer)
    session.commit()
    return True
