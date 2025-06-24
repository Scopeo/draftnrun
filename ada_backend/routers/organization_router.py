from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.organization_schema import OrganizationSecretResponse, OrganizationGetSecretKeysResponse
from ada_backend.services.organization_service import (
    upsert_secret_to_org_service,
    delete_secret_to_org_service,
    get_secret_keys_service,
)


router = APIRouter(
    prefix="/org",
)


@router.get(
    "/{org_id}/secrets",
    response_model=OrganizationGetSecretKeysResponse,
    summary="Get secret keys for organization",
    tags=["Organization"],
)
async def get_secret_keys(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    sqlaclhemy_db_session: AsyncSession = Depends(get_db),
) -> OrganizationGetSecretKeysResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return await get_secret_keys_service(sqlaclhemy_db_session, organization_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.put(
    "/{org_id}/secrets/{secret_key}",
    response_model=OrganizationSecretResponse,
    summary="Add or update secret to org",
    tags=["Organization"],
)
async def add_or_update_secret_to_organization(
    organization_id: UUID,
    secret_key: str,
    secret: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    sqlaclhemy_db_session: AsyncSession = Depends(get_db),
) -> OrganizationSecretResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return await upsert_secret_to_org_service(sqlaclhemy_db_session, organization_id, secret_key, secret)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.delete(
    "/{org_id}/secrets/{secret_key}",
    response_model=OrganizationSecretResponse,
    summary="Delete secret from org",
    tags=["Organization"],
)
async def delete_secret_from_organization(
    organization_id: UUID,
    secret_key: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    sqlaclhemy_db_session: AsyncSession = Depends(get_db),
) -> OrganizationSecretResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return await delete_secret_to_org_service(sqlaclhemy_db_session, organization_id, secret_key) # Await the service call
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e