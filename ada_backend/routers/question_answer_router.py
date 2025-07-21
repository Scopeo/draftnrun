from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.question_answer_schema import (
    QuestionAnswerCreate,
    QuestionAnswerResponse,
    QuestionAnswerUpdate,
    QuestionAnswerCreateList,
    QuestionAnswerResponseList,
)
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
)
from ada_backend.services.question_answer_service import (
    create_question_answer_service,
    create_questions_answers_service,
    delete_question_answer_service,
    get_question_answer_by_id_service,
    get_questions_answers_by_organization_and_project_service,
    update_question_answer_service,
)
from ada_backend.database.setup_db import get_db

router = APIRouter(prefix="/question-answers", tags=["Question Answers"])


@router.get(
    "/{organization_id}/projects/{project_id}",
    response_model=List[QuestionAnswerResponse],
    summary="Get Question-Answer Entries by Organization and Project",
)
def get_questions_answers_by_organization_and_project_endpoint(
    organization_id: UUID,
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value)),
    ],
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(100, ge=1, le=1000, description="Number of items per page"),
    session: Session = Depends(get_db),
) -> List[QuestionAnswerResponse]:
    """
    Get all question-answer entries for an organization and project with pagination.

    This endpoint allows users to retrieve question-answer pairs specific to a project
    for evaluation purposes. The data is paginated to handle large datasets efficiently.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_questions_answers_by_organization_and_project_service(
            session, organization_id, project_id, page, size
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.get(
    "/{organization_id}/projects/{project_id}/{question_answer_id}",
    response_model=QuestionAnswerResponse,
    summary="Get Question-Answer Entry by ID",
)
def get_question_answer_by_id_endpoint(
    organization_id: UUID,
    project_id: UUID,
    question_answer_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value)),
    ],
    session: Session = Depends(get_db),
) -> QuestionAnswerResponse:
    """
    Get a specific question-answer entry by ID.

    This endpoint allows users to retrieve a specific question-answer pair
    for detailed viewing or editing purposes.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_question_answer_by_id_service(session, question_answer_id, organization_id, project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post(
    "/{organization_id}/projects/{project_id}",
    response_model=QuestionAnswerResponse,
    summary="Create Question-Answer Entry",
)
def create_question_answer_endpoint(
    organization_id: UUID,
    project_id: UUID,
    question_answer_data: QuestionAnswerCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> QuestionAnswerResponse:
    """
    Create a new question-answer entry.

    This endpoint allows users to create new question-answer pairs for evaluation purposes.
    The entry will be associated with the specified organization and project.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_question_answer_service(session, organization_id, project_id, question_answer_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post(
    "/{organization_id}/projects/{project_id}/list",
    response_model=QuestionAnswerResponseList,
    summary="Create Multiple Question-Answer Entries",
)
def create_questions_answers_endpoint(
    organization_id: UUID,
    project_id: UUID,
    questions_answers_data: QuestionAnswerCreateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> QuestionAnswerResponseList:
    """
    Create multiple question-answer entries.

    This endpoint allows users to create multiple question-answer pairs at once
    for efficient data import. All entries will be associated with the specified
    organization and project.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_questions_answers_service(session, organization_id, project_id, questions_answers_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.put(
    "/{organization_id}/projects/{project_id}/{question_answer_id}",
    response_model=QuestionAnswerResponse,
    summary="Update Question-Answer Entry",
)
def update_question_answer_endpoint(
    organization_id: UUID,
    project_id: UUID,
    question_answer_id: UUID,
    question_answer_data: QuestionAnswerUpdate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> QuestionAnswerResponse:
    """
    Update an existing question-answer entry.

    This endpoint allows users to update existing question-answer pairs.
    Only the fields provided in the request will be updated.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return update_question_answer_service(
            session, question_answer_id, organization_id, project_id, question_answer_data
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.delete(
    "/{organization_id}/projects/{project_id}/{question_answer_id}",
    summary="Delete Question-Answer Entry",
)
def delete_question_answer_endpoint(
    organization_id: UUID,
    project_id: UUID,
    question_answer_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    """
    Delete a question-answer entry.

    This endpoint allows users to delete question-answer pairs.
    The deletion is permanent and cannot be undone.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        delete_question_answer_service(session, question_answer_id, organization_id, project_id)
        return {"message": f"Question-answer entry {question_answer_id} deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
