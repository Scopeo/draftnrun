"""
Variables router.

Endpoints for managing variable definitions and variable sets.
Extracted from project_router.py.
"""

import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ada_backend.database.models import VariableType
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_xor_verify_api_key,
)
from ada_backend.schemas.auth_schema import AuthenticatedEntity
from ada_backend.schemas.variable_schemas import (
    SetIdsResponse,
    VariableDefinitionResponse,
    VariableDefinitionUpsertRequest,
    VariableSetListResponse,
    VariableSetResponse,
    VariableSetUpsertRequest,
)
from ada_backend.services.errors import (
    ProjectNotFound,
    ProjectNotInOrganization,
)
from ada_backend.services.variables_service import (
    delete_definition_service,
    delete_set_service,
    get_set_ids_service,
    get_set_service,
    list_definitions_service,
    list_sets_service,
    upsert_definition_service,
    upsert_set_service,
)

LOGGER = logging.getLogger(__name__)

org_router = APIRouter(prefix="/org", tags=["Variables"])


# ---------------------------------------------------------------------------
# Org-scoped endpoints (JWT + API key via xor dependency)
# ---------------------------------------------------------------------------


@org_router.get(
    "/{organization_id}/variable-definitions",
    response_model=List[VariableDefinitionResponse],
    tags=["Variable Definitions"],
)
def list_org_variable_definitions(
    organization_id: UUID,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    project_id: Optional[UUID] = None,
    type: Annotated[VariableType | None, Query()] = None,
):
    return list_definitions_service(session, organization_id, project_id=project_id, var_type=type)


@org_router.put(
    "/{organization_id}/variable-definitions/{name}",
    response_model=VariableDefinitionResponse,
    tags=["Variable Definitions"],
)
def upsert_org_variable_definition(
    organization_id: UUID,
    name: str,
    body: VariableDefinitionUpsertRequest,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        return upsert_definition_service(session, organization_id, name, body)
    except (ProjectNotFound, ProjectNotInOrganization) as e:
        raise HTTPException(status_code=404, detail="Project not found") from e
    except IntegrityError as e:
        LOGGER.error(
            f"Integrity error upserting variable definition {name} for org {organization_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Invalid project reference") from e


@org_router.delete(
    "/{organization_id}/variable-definitions/{name}",
    tags=["Variable Definitions"],
)
def delete_org_variable_definition(
    organization_id: UUID,
    name: str,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    delete_definition_service(session, organization_id, name)
    return {"detail": "deleted"}


@org_router.get(
    "/{organization_id}/set-ids",
    response_model=SetIdsResponse,
    tags=["Variable Sets"],
)
def get_set_ids(
    organization_id: UUID,
    project_id: UUID,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        return get_set_ids_service(session, organization_id, project_id)
    except (ProjectNotFound, ProjectNotInOrganization) as e:
        raise HTTPException(status_code=404, detail="Project not found") from e


@org_router.get(
    "/{organization_id}/variable-sets",
    response_model=VariableSetListResponse,
    tags=["Variable Sets"],
)
def list_org_variable_sets(
    organization_id: UUID,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    variable_type: Annotated[VariableType | None, Query()] = None,
):
    return list_sets_service(session, organization_id, variable_type=variable_type)


@org_router.get(
    "/{organization_id}/variable-sets/{set_id}",
    response_model=VariableSetResponse,
    tags=["Variable Sets"],
)
def get_org_variable_set(
    organization_id: UUID,
    set_id: str,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    return get_set_service(session, organization_id, set_id)


@org_router.put(
    "/{organization_id}/variable-sets/{set_id}",
    response_model=VariableSetResponse,
    tags=["Variable Sets"],
)
def upsert_org_variable_set(
    organization_id: UUID,
    set_id: str,
    body: VariableSetUpsertRequest,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    return upsert_set_service(session, organization_id, set_id, body.values)


@org_router.delete(
    "/{organization_id}/variable-sets/{set_id}",
    tags=["Variable Sets"],
)
def delete_org_variable_set(
    organization_id: UUID,
    set_id: str,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    delete_set_service(session, organization_id, set_id)
    return {"detail": "deleted"}
