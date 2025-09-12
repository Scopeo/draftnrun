from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.category_schema import CategoryCreateSchema, CategoryResponse, CategoryUpdateSchema
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
)
from ada_backend.services.category_service import (
    create_category_service,
    delete_category_service,
    get_all_categories_service,
    get_category_by_id_service,
    update_category_service,
)

router = APIRouter(tags=["Categories"])


@router.get(path="/categories", response_model=list[CategoryResponse])
def get_all_categories(
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> list[CategoryResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_all_categories_service(session)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.get("/categories/{category_id}", response_model=CategoryResponse)
def get_category_by_id(
    category_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> CategoryResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_category_by_id_service(session, category_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/categories", response_model=CategoryResponse, summary="Create a new category")
def create_category(
    category: CategoryCreateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> CategoryResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return create_category_service(session, category)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}") from e


@router.patch("/categories/{category_id}", response_model=CategoryResponse, summary="Update a category")
def update_category(
    category: CategoryUpdateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    category_id: UUID = None,
    session: Session = Depends(get_db),
) -> CategoryResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return update_category_service(session, category_id, category)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}") from e


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return delete_category_service(session, category_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error: " + str(e)) from e
