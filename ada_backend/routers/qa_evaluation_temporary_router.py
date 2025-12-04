import logging
from uuid import UUID
from typing import Annotated, List

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.qa_evaluation_temporary_schema import (
    JudgeEvaluationResponse,
)
from ada_backend.services.errors import ProjectNotFound, LLMJudgeNotFound
from ada_backend.routers.auth_router import (
    user_has_access_to_project_dependency,
    UserRights,
)
from ada_backend.database.setup_db import get_db
from ada_backend.services.qa.qa_evaluation_temporary_service import (
    get_evaluations_by_version_output_service,
    run_judge_evaluation_service,
    delete_judge_evaluations_service,
)

router = APIRouter(tags=["QA Evaluation"])
LOGGER = logging.getLogger(__name__)


@router.get(
    "/projects/{project_id}/qa/version-outputs/{version_output_id}/evaluations",
    response_model=List[JudgeEvaluationResponse],
    summary="Get Evaluations by Version Output",
)
def get_evaluations_by_version_output_endpoint(
    project_id: UUID,
    version_output_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[JudgeEvaluationResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_evaluations_by_version_output_service(session=session, version_output_id=version_output_id)
    except Exception as e:
        LOGGER.error(
            f"Failed to get judge evaluations for "
            f"version_output {version_output_id} in project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations/run",
    response_model=JudgeEvaluationResponse,
    summary="Run Judge Evaluation on Version Output",
)
async def run_judge_evaluation_endpoint(
    project_id: UUID,
    judge_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
    version_output_id: UUID = Body(..., embed=True, description="Version output ID to evaluate"),
) -> JudgeEvaluationResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return await run_judge_evaluation_service(
            session=session,
            project_id=project_id,
            judge_id=judge_id,
            version_output_id=version_output_id,
        )
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except LLMJudgeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to run judge evaluation for judge {judge_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to run judge evaluation for judge {judge_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/projects/{project_id}/qa/evaluations",
    status_code=204,
    summary="Delete Judge Evaluations",
)
def delete_judge_evaluations_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
    ],
    session: Session = Depends(get_db),
    evaluation_ids: List[UUID] = Body(...),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        delete_judge_evaluations_service(session=session, evaluation_ids=evaluation_ids)
        return None
    except ValueError as e:
        LOGGER.error(f"Failed to delete judge evaluations for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete judge evaluations for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
