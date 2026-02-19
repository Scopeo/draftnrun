"""
Variables router.

Endpoints for managing variable definitions and variable sets.
Extracted from project_router.py.
"""

import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_xor_verify_api_key,
)
from ada_backend.schemas.variable_schemas import (
    VariableDefinitionResponse,
    VariableDefinitionUpsertRequest,
    VariableSetListResponse,
    VariableSetResponse,
    VariableSetUpsertRequest,
)
from ada_backend.services.errors import VariableDefinitionNotFound, VariableSetNotFound
from ada_backend.services.variables_service import (
    delete_definition_service,
    delete_set_service,
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
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        return list_definitions_service(session, organization_id)
    except Exception as e:
        LOGGER.error(f"Failed to list variable definitions for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        return upsert_definition_service(session, organization_id, name, body)
    except ValueError as e:
        LOGGER.error(f"Failed to upsert variable definition {name} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to upsert variable definition {name} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@org_router.delete(
    "/{organization_id}/variable-definitions/{name}",
    tags=["Variable Definitions"],
)
def delete_org_variable_definition(
    organization_id: UUID,
    name: str,
    auth: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        delete_definition_service(session, organization_id, name)
    except VariableDefinitionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to delete variable definition {name} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
    return {"detail": "deleted"}


@org_router.get(
    "/{organization_id}/variable-sets",
    response_model=VariableSetListResponse,
    tags=["Variable Sets"],
)
def list_org_variable_sets(
    organization_id: UUID,
    auth: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        return list_sets_service(session, organization_id)
    except Exception as e:
        LOGGER.error(f"Failed to list variable sets for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@org_router.get(
    "/{organization_id}/variable-sets/{set_id}",
    response_model=VariableSetResponse,
    tags=["Variable Sets"],
)
def get_org_variable_set(
    organization_id: UUID,
    set_id: str,
    auth: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        return get_set_service(session, organization_id, set_id)
    except VariableSetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to get variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        return upsert_set_service(session, organization_id, set_id, body.values)
    except ValueError as e:
        LOGGER.error(f"Failed to upsert variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to upsert variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@org_router.delete(
    "/{organization_id}/variable-sets/{set_id}",
    tags=["Variable Sets"],
)
def delete_org_variable_set(
    organization_id: UUID,
    set_id: str,
    auth: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        delete_set_service(session, organization_id, set_id)
    except VariableSetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to delete variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
    return {"detail": "deleted"}
