from sqlalchemy.orm import Session

from ada_backend.repositories.categories_repository import (
    create_category,
    delete_category,
    get_all_categories,
    get_category,
    update_category,
)
from ada_backend.schemas.category_schema import CategoryCreateSchema, CategoryResponse, CategoryUpdateSchema
from ada_backend.services.errors import CategoryNotFound, DuplicateCategoryName, InvalidCategoryUpdate


def get_all_categories_service(session: Session) -> list[CategoryResponse]:
    categories = get_all_categories(session)
    return [
        CategoryResponse(id=category.id, name=category.name, description=category.description)
        for category in categories
    ]


def get_category_by_id_service(session: Session, category_id: str) -> CategoryResponse | None:
    category = get_category(session, category_id)
    if not category:
        raise CategoryNotFound(category_id)
    return CategoryResponse.model_validate(category, from_attributes=True) if category else None


def create_category_service(session: Session, category: CategoryCreateSchema) -> CategoryResponse:
    categories = get_all_categories(session)
    if any(cat.name == category.name for cat in categories):
        raise DuplicateCategoryName(category.name)
    category = create_category(session, category.name, category.description)
    return CategoryResponse(id=category.id, name=category.name, description=category.description)


def update_category_service(
    session: Session,
    category_id: str,
    category: CategoryUpdateSchema | None = None,
) -> CategoryResponse:
    if category.name is None and category.description is None:
        raise InvalidCategoryUpdate()
    existing_categories = get_all_categories(session)
    if any(cat.name == category.name and str(cat.id) != category_id for cat in existing_categories):
        raise DuplicateCategoryName(category.name)
    category = get_category(session, category_id)
    if not category:
        raise CategoryNotFound(category_id)
    category = update_category(session, category_id, category.name, category.description)
    return category


def delete_category_service(session: Session, category_id: str) -> None:
    category = get_category(session, category_id)
    if category:
        delete_category(session, category_id)
