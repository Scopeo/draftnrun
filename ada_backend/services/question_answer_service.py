import logging
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.question_answer_repository import (
    create_question_answer,
    create_questions_answers,
    delete_question_answer,
    get_question_answer_by_id,
    get_questions_answers_with_pagination,
    update_question_answer,
)
from ada_backend.schemas.question_answer_schema import (
    QuestionAnswerCreate,
    QuestionAnswerResponse,
    QuestionAnswerUpdate,
    QuestionAnswerCreateList,
    QuestionAnswerResponseList,
)

LOGGER = logging.getLogger(__name__)


def get_questions_answers_by_organization_and_project_service(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
    page: int = 1,
    size: int = 100,
) -> List[QuestionAnswerResponse]:
    """
    Get all question-answer entries for an organization and project with pagination.

    Args:
        session (Session): SQLAlchemy session
        organization_id (UUID): ID of the organization
        project_id (UUID): ID of the project
        page (int): Page number (1-based)
        size (int): Number of items per page

    Returns:
        List[QuestionAnswerResponse]: List of question-answer entries
    """
    try:
        questions_answers, _ = get_questions_answers_with_pagination(session, organization_id, project_id, page, size)

        return [QuestionAnswerResponse.model_validate(qa) for qa in questions_answers]
    except Exception as e:
        LOGGER.error(f"Error in get_questions_answers_by_organization_and_project_service: {str(e)}")
        raise ValueError(f"Failed to get question-answer entries: {str(e)}") from e
    finally:
        session.close()


def get_question_answer_by_id_service(
    session: Session,
    question_answer_id: UUID,
    organization_id: UUID,
    project_id: UUID,
) -> QuestionAnswerResponse:
    """
    Get a specific question-answer entry by ID.

    Args:
        session (Session): SQLAlchemy session
        question_answer_id (UUID): ID of the question-answer entry
        organization_id (UUID): ID of the organization
        project_id (UUID): ID of the project

    Returns:
        QuestionAnswerResponse: The question-answer entry

    Raises:
        ValueError: If the question-answer entry is not found
    """
    try:
        question_answer = get_question_answer_by_id(session, question_answer_id, organization_id, project_id)
        if not question_answer:
            raise ValueError(f"Question-answer entry {question_answer_id} not found")

        return QuestionAnswerResponse.model_validate(question_answer)
    except Exception as e:
        LOGGER.error(f"Error in get_question_answer_by_id_service: {str(e)}")
        raise ValueError(f"Failed to get question-answer entry: {str(e)}") from e
    finally:
        session.close()


def create_question_answer_service(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
    question_answer_data: QuestionAnswerCreate,
) -> QuestionAnswerResponse:
    """
    Create a new question-answer entry.

    Args:
        session (Session): SQLAlchemy session
        organization_id (UUID): ID of the organization
        project_id (UUID): ID of the project
        question_answer_data (QuestionAnswerCreate): Question-answer data to create

    Returns:
        QuestionAnswerResponse: The created question-answer entry
    """
    try:
        question_answer = create_question_answer(
            session,
            organization_id,
            project_id,
            question_answer_data.question,
            question_answer_data.groundtruth,
        )

        LOGGER.info(f"Question-answer entry created for organization {organization_id} and project {project_id}")
        return QuestionAnswerResponse.model_validate(question_answer)
    except Exception as e:
        LOGGER.error(f"Error in create_question_answer_service: {str(e)}")
        raise ValueError(f"Failed to create question-answer entry: {str(e)}") from e
    finally:
        session.close()


def create_questions_answers_service(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
    questions_answers_data: QuestionAnswerCreateList,
) -> QuestionAnswerResponseList:
    """
    Create multiple question-answer entries.

    Args:
        session (Session): SQLAlchemy session
        organization_id (UUID): ID of the organization
        project_id (UUID): ID of the project
        questions_answers_data (QuestionAnswerCreateList): Question-answer data to create

    Returns:
        QuestionAnswerResponseList: The created question-answer entries
    """
    try:
        created_question_answers = create_questions_answers(
            session,
            organization_id,
            project_id,
            questions_answers_data.questions_answers,
        )

        LOGGER.info(
            f"Created {len(created_question_answers)} question-answer "
            f"entries for organization {organization_id} and project {project_id}"
        )

        return QuestionAnswerResponseList(
            questions_answers=[QuestionAnswerResponse.model_validate(qa) for qa in created_question_answers]
        )
    except Exception as e:
        LOGGER.error(f"Error in create_questions_answers_service: {str(e)}")
        raise ValueError(f"Failed to create question-answer entries: {str(e)}") from e
    finally:
        session.close()


def update_question_answer_service(
    session: Session,
    question_answer_id: UUID,
    organization_id: UUID,
    project_id: UUID,
    question_answer_data: QuestionAnswerUpdate,
) -> QuestionAnswerResponse:
    """
    Update an existing question-answer entry.

    Args:
        session (Session): SQLAlchemy session
        question_answer_id (UUID): ID of the question-answer entry
        organization_id (UUID): ID of the organization
        project_id (UUID): ID of the project
        question_answer_data (QuestionAnswerUpdate): Question-answer data to update

    Returns:
        QuestionAnswerResponse: The updated question-answer entry

    Raises:
        ValueError: If the question-answer entry is not found
    """
    try:
        question_answer = update_question_answer(
            session,
            question_answer_id,
            organization_id,
            project_id,
            question_answer_data.question,
            question_answer_data.groundtruth,
        )

        if not question_answer:
            raise ValueError(f"Question-answer entry {question_answer_id} not found")

        LOGGER.info(
            f"Question-answer entry {question_answer_id} updated for organization "
            f"{organization_id} and project {project_id}"
        )
        return QuestionAnswerResponse.model_validate(question_answer)
    except ValueError:
        raise
    except Exception as e:
        LOGGER.error(f"Error in update_question_answer_service: {str(e)}")
        raise ValueError(f"Failed to update question-answer entry: {str(e)}") from e
    finally:
        session.close()


def delete_question_answer_service(
    session: Session,
    question_answer_id: UUID,
    organization_id: UUID,
    project_id: UUID,
) -> None:
    """
    Delete a question-answer entry.

    Args:
        session (Session): SQLAlchemy session
        question_answer_id (UUID): ID of the question-answer entry
        organization_id (UUID): ID of the organization
        project_id (UUID): ID of the project

    Raises:
        ValueError: If the question-answer entry is not found
    """
    try:
        success = delete_question_answer(session, question_answer_id, organization_id, project_id)
        if not success:
            raise ValueError(f"Question-answer entry {question_answer_id} not found")

        LOGGER.info(
            f"Question-answer entry {question_answer_id} deleted for organization {organization_id} "
            f"and project {project_id}"
        )
    except ValueError:
        raise
    except Exception as e:
        LOGGER.error(f"Error in delete_question_answer_service: {str(e)}")
        raise ValueError(f"Failed to delete question-answer entry: {str(e)}") from e
    finally:
        session.close()
