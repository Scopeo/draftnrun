from fastapi import HTTPException
from sqlalchemy.orm import Session

from ada_backend.repositories.categories_repository import (
    create_category,
    delete_category,
    get_all_categories,
    get_category_by_id,
    update_category,
)
from ada_backend.schemas.category_schema import CategoryCreateSchema, CategoryResponse, CategoryUpdateSchema


def get_all_categories_service(session: Session) -> list[CategoryResponse]:
    categories = get_all_categories(session)
    return [
        CategoryResponse(id=category.id, name=category.name, description=category.description)
        for category in categories
    ]


def get_category_by_id_service(session: Session, category_id: str) -> CategoryResponse | None:
    category = get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return CategoryResponse.model_validate(category, from_attributes=True) if category else None


def create_category_service(session: Session, category: CategoryCreateSchema) -> CategoryResponse:
    categories = get_all_categories(session)
    if any(cat.name == category.name for cat in categories):
        raise ValueError("Category with this name already exists")
    category = create_category(session, category.name, category.description)
    return CategoryResponse(id=category.id, name=category.name, description=category.description)


def update_category_service(
    session: Session,
    category_id: str,
    category: CategoryUpdateSchema | None = None,
) -> CategoryResponse:
    if category.name is None and category.description is None:
        raise ValueError("At least one field (name or description) must be provided for update")
    existings_categories = get_all_categories(session)
    if any(cat.name == category.name and str(cat.id) != category_id for cat in existings_categories):
        raise ValueError("Category with this name already exists")
    category = update_category(session, category_id, category.name, category.description)
    return category


def delete_category_service(session: Session, category_id: str) -> None:
    category = get_category_by_id(session, category_id)
    if not category:
        raise ValueError("Category not found")
    try:
        delete_category(session, category_id)
    except Exception as e:
        raise ValueError(f"Failed to delete category : {str(e)}") from e
