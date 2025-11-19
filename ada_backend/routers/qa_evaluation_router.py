import logging
from uuid import UUID
from typing import Annotated, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.qa_evaluation_schema import (
    LLMJudgeCreate,
    LLMJudgeResponse,
    LLMJudgeUpdate,
    JudgeEvaluationCreate,
    JudgeEvaluationResponse,
    JudgeEvaluationRunResponse,
)
from ada_backend.services.errors import LLMJudgeNotFound
from ada_backend.routers.auth_router import (
    user_has_access_to_project_dependency,
    UserRights,
)
from ada_backend.database.setup_db import get_db
from ada_backend.services.qa_evaluation_service import (
    create_llm_judge_service,
    get_llm_judges_by_project_service,
    update_llm_judge_service,
    delete_llm_judges_service,
    create_judge_evaluation_service,
    get_judge_evaluations_by_judge_service,
    get_judge_evaluations_by_version_output_service,
    run_judge_evaluation_service,
    delete_judge_evaluations_service,
)

router = APIRouter(tags=["QA Evaluation"])
LOGGER = logging.getLogger(__name__)


@router.get(
    "/projects/{project_id}/qa/llm-judges",
    response_model=List[LLMJudgeResponse],
    summary="Get LLM Judges by Project",
)
def get_llm_judges_by_project_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[LLMJudgeResponse]:
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
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


@router.patch(
    "/projects/{project_id}/qa/llm-judges/{judge_id}",
    response_model=LLMJudgeResponse,
    summary="Update LLM Judge",
)
def update_llm_judge_endpoint(
    project_id: UUID,
    judge_id: UUID,
    judge_data: LLMJudgeUpdate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return update_llm_judge_service(
            session=session,
            project_id=project_id,
            judge_id=judge_id,
            judge_data=judge_data,
        )
    except LLMJudgeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(f"Failed to update LLM judge {judge_id} for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to update LLM judge {judge_id} for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/projects/{project_id}/qa/llm-judges",
    status_code=204,
    summary="Delete LLM Judges",
)
def delete_llm_judges_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
    ],
    session: Session = Depends(get_db),
    judge_ids: List[UUID] = Body(...),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        delete_llm_judges_service(session=session, project_id=project_id, judge_ids=judge_ids)
        return None
    except ValueError as e:
        LOGGER.error(f"Failed to delete LLM judges for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete LLM judges for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations",
    response_model=JudgeEvaluationResponse,
    summary="Create Judge Evaluation",
)
def create_judge_evaluation_endpoint(
    project_id: UUID,
    judge_id: UUID,
    evaluation_data: JudgeEvaluationCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
    ],
    session: Session = Depends(get_db),
) -> JudgeEvaluationResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_judge_evaluation_service(
            session=session,
            project_id=project_id,
            judge_id=judge_id,
            evaluation_data=evaluation_data,
        )
    except LLMJudgeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to create judge evaluation for judge {judge_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to create judge evaluation for judge {judge_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations",
    response_model=List[JudgeEvaluationResponse],
    summary="Get Judge Evaluations by Judge",
)
def get_judge_evaluations_by_judge_endpoint(
    project_id: UUID,
    judge_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[JudgeEvaluationResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_judge_evaluations_by_judge_service(session=session, judge_id=judge_id)
    except ValueError as e:
        LOGGER.error(
            f"Failed to get judge evaluations for judge {judge_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get judge evaluations for judge {judge_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/projects/{project_id}/qa/version-outputs/evaluations",
    response_model=List[JudgeEvaluationResponse],
    summary="Get Judge Evaluations by Version Output",
)
def get_judge_evaluations_by_version_output_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
    version_output_id: UUID = Query(..., description="Version output ID to get evaluations for"),
) -> List[JudgeEvaluationResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_judge_evaluations_by_version_output_service(session=session, version_output_id=version_output_id)
    except ValueError as e:
        LOGGER.error(
            f"Failed to get judge evaluations for version_output {version_output_id} in project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get judge evaluations for version_output {version_output_id} in project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations/run",
    response_model=JudgeEvaluationRunResponse,
    summary="Run Judge Evaluation on Version Outputs",
)
async def run_judge_evaluation_endpoint(
    project_id: UUID,
    judge_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
    version_output_ids: List[UUID] = Body(..., description="List of version output IDs to evaluate"),
) -> JudgeEvaluationRunResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return await run_judge_evaluation_service(
            session=session,
            project_id=project_id,
            judge_id=judge_id,
            version_output_ids=version_output_ids,
        )
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
        delete_judge_evaluations_service(session=session, project_id=project_id, evaluation_ids=evaluation_ids)
        return None
    except ValueError as e:
        LOGGER.error(f"Failed to delete judge evaluations for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete judge evaluations for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
