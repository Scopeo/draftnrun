from typing import Annotated
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import get_user_from_supabase_token
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.global_secret_schema import GlobalSecretListItem, UpsertGlobalSecretRequest
from ada_backend.services.global_secret_service import (
    list_for_admin,
    upsert_for_admin,
    delete_for_admin,
)
from ada_backend.services.user_roles_service import is_user_super_admin


LOGGER = logging.getLogger(__name__)


router = APIRouter(prefix="/admin-tools/settings-secrets", tags=["Admin Tools"])


async def _ensure_superadmin(user: SupabaseUser) -> None:
    is_super = await is_user_super_admin(user)
    if not is_super:
        raise HTTPException(status_code=403, detail="Super admin required")


@router.get("/", response_model=list[GlobalSecretListItem])
async def list_global_settings_secrets(
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    await _ensure_superadmin(user)
    return list_for_admin(session)


@router.post("/")
async def upsert_global_settings_secret(
    payload: UpsertGlobalSecretRequest,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    await _ensure_superadmin(user)
    try:
        upsert_for_admin(session, key=payload.key, secret=payload.secret)
        return {"status": "ok"}
    except ValueError as e:
        LOGGER.error(f"Failed to upsert global secret with key {payload.key}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e


@router.delete("/{key}")
async def delete_global_settings_secret(
    key: str,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    await _ensure_superadmin(user)
    try:
        delete_for_admin(session, key=key)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
