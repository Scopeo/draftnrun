import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.prompt_schema import (
    PromptCreateSchema,
    PromptDetailResponseSchema,
    PromptDiffResponseSchema,
    PromptPinRequestSchema,
    PromptPinResponseSchema,
    PromptResponseSchema,
    PromptUsageSchema,
    PromptVersionCreateSchema,
    PromptVersionResponseSchema,
    PromptVersionSummarySchema,
)
from ada_backend.services.prompt_service import (
    create_prompt_service,
    create_prompt_version_service,
    delete_prompt_service,
    diff_prompt_versions_service,
    get_project_prompt_pins_service,
    get_prompt_detail_service,
    get_prompt_usages_service,
    get_prompt_version_detail_service,
    list_prompt_versions_service,
    list_prompts_service,
    pin_prompt_to_port_service,
    unpin_prompt_from_port_service,
)

router = APIRouter(tags=["Prompts"])
LOGGER = logging.getLogger(__name__)


@router.post("/orgs/{org_id}/prompts", response_model=PromptResponseSchema, status_code=201)
def create_prompt(
    org_id: UUID,
    payload: PromptCreateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> PromptResponseSchema:
    return create_prompt_service(
        session=session,
        organization_id=org_id,
        name=payload.name,
        content=payload.content,
        description=payload.description,
        sections=payload.sections,
        created_by=user.id,
    )


@router.get("/orgs/{org_id}/prompts", response_model=list[PromptResponseSchema])
def list_prompts(
    org_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> list[PromptResponseSchema]:
    return list_prompts_service(session, org_id)


@router.get("/orgs/{org_id}/prompts/{prompt_id}", response_model=PromptDetailResponseSchema)
def get_prompt(
    org_id: UUID,
    prompt_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> PromptDetailResponseSchema:
    return get_prompt_detail_service(session, prompt_id, organization_id=org_id)


@router.delete("/orgs/{org_id}/prompts/{prompt_id}", status_code=204)
def delete_prompt_endpoint(
    org_id: UUID,
    prompt_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    delete_prompt_service(session, prompt_id, organization_id=org_id)


@router.post(
    "/orgs/{org_id}/prompts/{prompt_id}/versions",
    response_model=PromptVersionResponseSchema,
    status_code=201,
)
def create_version(
    org_id: UUID,
    prompt_id: UUID,
    payload: PromptVersionCreateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> PromptVersionResponseSchema:
    return create_prompt_version_service(
        session=session,
        prompt_id=prompt_id,
        name=payload.name,
        content=payload.content,
        description=payload.description,
        change_description=payload.change_description,
        sections=payload.sections,
        created_by=user.id,
        organization_id=org_id,
    )


@router.get(
    "/orgs/{org_id}/prompts/{prompt_id}/versions",
    response_model=list[PromptVersionSummarySchema],
)
def list_versions(
    org_id: UUID,
    prompt_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> list[PromptVersionSummarySchema]:
    return list_prompt_versions_service(session, prompt_id, organization_id=org_id)


@router.get(
    "/orgs/{org_id}/prompts/{prompt_id}/versions/{version_id}",
    response_model=PromptVersionResponseSchema,
)
def get_version(
    org_id: UUID,
    prompt_id: UUID,
    version_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> PromptVersionResponseSchema:
    return get_prompt_version_detail_service(session, version_id, organization_id=org_id)


@router.get(
    "/orgs/{org_id}/prompts/{prompt_id}/diff",
    response_model=PromptDiffResponseSchema,
)
def diff_versions(
    org_id: UUID,
    prompt_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    from_version: UUID = Query(..., alias="from"),
    to_version: UUID = Query(..., alias="to"),
    session: Session = Depends(get_db),
) -> PromptDiffResponseSchema:
    return diff_prompt_versions_service(session, from_version, to_version, organization_id=org_id)


@router.get("/orgs/{org_id}/prompts/{prompt_id}/usages", response_model=list[PromptUsageSchema])
def get_usages(
    org_id: UUID,
    prompt_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> list[PromptUsageSchema]:
    return get_prompt_usages_service(session, prompt_id, organization_id=org_id)


@router.put(
    "/projects/{project_id}/graph/{graph_runner_id}/components/{ci_id}/ports/{port_name}/prompt-pin",
    status_code=204,
)
def pin_prompt(
    project_id: UUID,
    graph_runner_id: UUID,
    ci_id: UUID,
    port_name: str,
    payload: PromptPinRequestSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    pin_prompt_to_port_service(session, ci_id, port_name, payload.prompt_version_id, graph_runner_id)


@router.delete(
    "/projects/{project_id}/graph/{graph_runner_id}/components/{ci_id}/ports/{port_name}/prompt-pin",
    status_code=204,
)
def unpin_prompt(
    project_id: UUID,
    graph_runner_id: UUID,
    ci_id: UUID,
    port_name: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    unpin_prompt_from_port_service(session, ci_id, port_name, graph_runner_id)


@router.get("/projects/{project_id}/prompt-pins", response_model=list[PromptPinResponseSchema])
def get_project_pins(
    project_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> list[PromptPinResponseSchema]:
    return get_project_prompt_pins_service(session, project_id)
