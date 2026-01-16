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
        CategoryResponse(
            id=category.id,
            name=category.name,
            description=category.description,
            icon=category.icon,
            display_order=category.display_order,
        )
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
    new_category = create_category(session, category.name, category.description, category.icon, category.display_order)
    return CategoryResponse(
        id=new_category.id,
        name=new_category.name,
        description=new_category.description,
        icon=new_category.icon,
        display_order=new_category.display_order,
    )


def update_category_service(
    session: Session,
    category_id: str,
    category: CategoryUpdateSchema | None = None,
) -> CategoryResponse:
    if (
        category.name is None
        and category.description is None
        and category.icon is None
        and category.display_order is None
    ):
        raise InvalidCategoryUpdate()
    existing_categories = get_all_categories(session)
    if any(cat.name == category.name and str(cat.id) != category_id for cat in existing_categories):
        raise DuplicateCategoryName(category.name)
    existing_category = get_category(session, category_id)
    if not existing_category:
        raise CategoryNotFound(category_id)
    updated_category = update_category(
        session, category_id, category.name, category.description, category.icon, category.display_order
    )
    return CategoryResponse.model_validate(updated_category, from_attributes=True)


def delete_category_service(session: Session, category_id: str) -> None:
    category = get_category(session, category_id)
    if category:
        delete_category(session, category_id)
