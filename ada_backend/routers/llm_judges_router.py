import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.models import EvaluationType
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    get_user_from_supabase_token,
    user_has_access_to_organization_dependency,
    user_has_access_to_project_dependency,
)
from ada_backend.routers.router_utils import resolve_organization_id
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.llm_judges_schema import (
    LLMJudgeCreate,
    LLMJudgeProjectAssociationRequest,
    LLMJudgeResponse,
    LLMJudgeTemplate,
    LLMJudgeUpdate,
)
from ada_backend.services.errors import LLMJudgeNotFound, ProjectNotFound
from ada_backend.services.qa.llm_judges_service import (
    create_llm_judge_service,
    delete_llm_judges_service,
    get_llm_judge_defaults_service,
    get_llm_judges_by_organization_service,
    get_llm_judges_by_project_service,
    set_judge_projects_service,
    update_llm_judge_service,
)

router = APIRouter(tags=["QA Evaluation"])
LOGGER = logging.getLogger(__name__)


@router.get(
    "/organizations/{organization_id}/qa/llm-judges",
    response_model=List[LLMJudgeResponse],
    summary="Get LLM Judges by Organization",
)
def get_llm_judges_by_organization_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[LLMJudgeResponse]:
    try:
        return get_llm_judges_by_organization_service(session=session, organization_id=organization_id)
    except Exception as e:
        LOGGER.error(f"Failed to get LLM judges for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/qa/llm-judges/defaults",
    response_model=LLMJudgeTemplate,
    summary="Get template with default values for LLM Judge creation",
)
def get_llm_judge_defaults(
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    evaluation_type: EvaluationType = Query(default=EvaluationType.BOOLEAN, description="Evaluation type"),
) -> LLMJudgeTemplate:
    return get_llm_judge_defaults_service(evaluation_type=evaluation_type)


@router.post(
    "/organizations/{organization_id}/qa/llm-judges",
    response_model=LLMJudgeResponse,
    summary="Create LLM Judge",
)
def create_llm_judge_endpoint(
    organization_id: UUID,
    judge_data: LLMJudgeCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    try:
        return create_llm_judge_service(session=session, organization_id=organization_id, judge_data=judge_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create LLM judge for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/organizations/{organization_id}/qa/llm-judges/{judge_id}",
    response_model=LLMJudgeResponse,
    summary="Update LLM Judge",
)
def update_llm_judge_endpoint(
    organization_id: UUID,
    judge_id: UUID,
    judge_data: LLMJudgeUpdate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    try:
        return update_llm_judge_service(
            session=session,
            organization_id=organization_id,
            judge_id=judge_id,
            judge_data=judge_data,
        )
    except LLMJudgeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to update LLM judge {judge_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/organizations/{organization_id}/qa/llm-judges",
    status_code=204,
    summary="Delete LLM Judges",
)
def delete_llm_judges_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    judge_ids: List[UUID] = Body(...),
):
    try:
        delete_llm_judges_service(session=session, organization_id=organization_id, judge_ids=judge_ids)
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete LLM judges for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put(
    "/organizations/{organization_id}/qa/llm-judges/{judge_id}/projects",
    response_model=LLMJudgeResponse,
    summary="Set Judge Project Associations",
)
def set_judge_projects_endpoint(
    organization_id: UUID,
    judge_id: UUID,
    body: LLMJudgeProjectAssociationRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    try:
        return set_judge_projects_service(session, organization_id, judge_id, body.project_ids)
    except (LLMJudgeNotFound, ProjectNotFound) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to set judge projects: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# ── Deprecated project-scoped endpoints (use org-scoped equivalents) ──────────


@router.get(
    "/projects/{project_id}/qa/llm-judges",
    response_model=List[LLMJudgeResponse],
    summary="Get LLM Judges by Project",
    deprecated=True,
)
def get_llm_judges_by_project_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[LLMJudgeResponse]:
    try:
        return get_llm_judges_by_project_service(session=session, project_id=project_id)
    except Exception as e:
        LOGGER.error(f"Failed to get LLM judges for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/llm-judges",
    response_model=LLMJudgeResponse,
    summary="Create LLM Judge (deprecated — use org-scoped endpoint)",
    deprecated=True,
)
def create_llm_judge_by_project_endpoint(
    project_id: UUID,
    judge_data: LLMJudgeCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    try:
        organization_id = resolve_organization_id(session, project_id)
        judge_response = create_llm_judge_service(
            session=session, organization_id=organization_id, judge_data=judge_data
        )
        return set_judge_projects_service(
            session=session,
            organization_id=organization_id,
            judge_id=judge_response.id,
            project_ids=[project_id],
        )
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e


@router.patch(
    "/projects/{project_id}/qa/llm-judges/{judge_id}",
    response_model=LLMJudgeResponse,
    summary="Update LLM Judge (deprecated — use org-scoped endpoint)",
    deprecated=True,
)
def update_llm_judge_by_project_endpoint(
    project_id: UUID,
    judge_id: UUID,
    judge_data: LLMJudgeUpdate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    try:
        organization_id = resolve_organization_id(session, project_id)
        return update_llm_judge_service(
            session=session,
            organization_id=organization_id,
            judge_id=judge_id,
            judge_data=judge_data,
        )
    except (ProjectNotFound, LLMJudgeNotFound) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to update LLM judge {judge_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/projects/{project_id}/qa/llm-judges",
    status_code=204,
    summary="Delete LLM Judges (deprecated — use org-scoped endpoint)",
    deprecated=True,
)
def delete_llm_judges_by_project_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    judge_ids: List[UUID] = Body(...),
):
    try:
        organization_id = resolve_organization_id(session, project_id)
        delete_llm_judges_service(session=session, organization_id=organization_id, judge_ids=judge_ids)
        return None
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
