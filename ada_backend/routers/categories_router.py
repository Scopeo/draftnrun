import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    ensure_super_admin_dependency,
    get_user_from_supabase_token,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.category_schema import CategoryCreateSchema, CategoryResponse, CategoryUpdateSchema
from ada_backend.services.category_service import (
    create_category_service,
    delete_category_service,
    get_all_categories_service,
    get_category_by_id_service,
    update_category_service,
)
from ada_backend.services.errors import CategoryNotFound, DuplicateCategoryName, InvalidCategoryUpdate

router = APIRouter(tags=["Categories"])
LOGGER = logging.getLogger(__name__)


@router.get(path="/categories", response_model=list[CategoryResponse])
def get_all_categories(
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
) -> list[CategoryResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_all_categories_service(session)
    except Exception as e:
        LOGGER.error(f"Failed to list categories: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/categories/{category_id}", response_model=CategoryResponse)
def get_category_by_id(
    category_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> CategoryResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_category_by_id_service(session, category_id)
    except CategoryNotFound:
        raise HTTPException(status_code=404, detail="Resource not found")
    except Exception as e:
        LOGGER.error(f"Failed to get category {category_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/categories", response_model=CategoryResponse, summary="Create a new category")
def create_category(
    category: CategoryCreateSchema,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
) -> CategoryResponse:
    try:
        return create_category_service(session, category)
    except DuplicateCategoryName as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to create category: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch("/categories/{category_id}", response_model=CategoryResponse, summary="Update a category")
def update_category(
    category: CategoryUpdateSchema,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    category_id: UUID = None,
    session: Session = Depends(get_db),
) -> CategoryResponse:
    try:
        return update_category_service(session, category_id, category)
    except CategoryNotFound:
        raise HTTPException(status_code=404, detail="Category not found")
    except DuplicateCategoryName as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidCategoryUpdate as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to update category {category_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: UUID,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
) -> None:
    try:
        delete_category_service(session, category_id)
    except Exception as e:
        LOGGER.error(f"Failed to delete category {category_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e

    return Response(status_code=status.HTTP_204_NO_CONTENT)
