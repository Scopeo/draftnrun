import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_xor_verify_api_key
from ada_backend.schemas.organization_schema import OrganizationGetSecretKeysResponse, OrganizationSecretResponse
from ada_backend.services.organization_service import (
    delete_secret_to_org_service,
    get_secret_keys_service,
    upsert_secret_to_org_service,
)

router = APIRouter(
    prefix="/org",
)
LOGGER = logging.getLogger(__name__)


@router.get(
    "/{organization_id}/secrets",
    response_model=OrganizationGetSecretKeysResponse,
    summary="Get secret keys for organization",
    tags=["Organization"],
)
def get_secret_keys(
    organization_id: UUID,
    auth: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    sqlaclhemy_db_session: Session = Depends(get_db),
) -> OrganizationGetSecretKeysResponse:
    try:
        return get_secret_keys_service(sqlaclhemy_db_session, organization_id)
    except ValueError as e:
        LOGGER.error(f"Failed to get organization secrets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get organization secrets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put(
    "/{organization_id}/secrets/{secret_key}",
    response_model=OrganizationSecretResponse,
    summary="Add or update secret to org",
    tags=["Organization"],
)
async def add_or_update_secret_to_organization(
    organization_id: UUID,
    secret_key: str,
    secret: str,
    auth: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    sqlaclhemy_db_session: Session = Depends(get_db),
) -> OrganizationSecretResponse:
    try:
        return await upsert_secret_to_org_service(sqlaclhemy_db_session, organization_id, secret_key, secret)
    except ValueError as e:
        LOGGER.error(
            f"Failed to upsert secret {secret_key} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to upsert secret {secret_key} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/{organization_id}/secrets/{secret_key}",
    response_model=OrganizationSecretResponse,
    summary="Delete secret from org",
    tags=["Organization"],
)
def delete_secret_from_organization(
    organization_id: UUID,
    secret_key: str,
    auth: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    sqlaclhemy_db_session: Session = Depends(get_db),
) -> OrganizationSecretResponse:
    try:
        return delete_secret_to_org_service(sqlaclhemy_db_session, organization_id, secret_key)
    except ValueError as e:
        LOGGER.error(
            f"Failed to delete secret {secret_key} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to delete secret {secret_key} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e
