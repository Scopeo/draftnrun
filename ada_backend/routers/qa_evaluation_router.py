import logging
from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.qa_evaluation_schema import (
    LLMJudgeCreate,
    LLMJudgeResponse,
    LLMJudgeListResponse,
)
from ada_backend.routers.auth_router import (
    user_has_access_to_project_dependency,
    UserRights,
)
from ada_backend.database.setup_db import get_db
from ada_backend.services.qa_evaluation_service import (
    create_llm_judge_service,
    get_llm_judges_by_project_service,
)

router = APIRouter(tags=["Quality Assurance"])
LOGGER = logging.getLogger(__name__)


@router.get(
    "/projects/{project_id}/qa/llm-judges",
    response_model=LLMJudgeListResponse,
    summary="Get LLM Judges by Project",
)
def get_llm_judges_by_project_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeListResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_llm_judges_by_project_service(session=session, project_id=project_id)
    except ValueError as e:
        LOGGER.error(f"Failed to get LLM judges for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get LLM judges for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/llm-judges",
    response_model=LLMJudgeResponse,
    summary="Create LLM Judge",
)
def create_llm_judge_endpoint(
    project_id: UUID,
    judge_data: LLMJudgeCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_llm_judge_service(session=session, project_id=project_id, judge_data=judge_data)
    except ValueError as e:
        LOGGER.error(f"Failed to create LLM judge for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create LLM judge for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
