from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def get_all_categories(session: Session) -> List[db.Category]:
    return session.query(db.Category).order_by(db.Category.display_order).all()


def get_category(session: Session, category_id: str) -> db.Category:
    return session.query(db.Category).filter(db.Category.id == category_id).first()


def fetch_associated_category_ids(session: Session, component_id: UUID) -> List[UUID]:
    """
    Retrieve category IDs associated with a component.

    Args:
        session (Session): SQLAlchemy session.
        component_id (UUID): ID of the component.

    Returns:
        List[UUID]: List of category IDs associated with the component.
    """
    category_ids = (
        session.query(db.ComponentCategory.category_id)
        .filter(db.ComponentCategory.component_id == component_id)
        .all()
    )
    return [cat_id[0] for cat_id in category_ids] if category_ids else []


def create_category(
    session: Session,
    name: str,
    description: str | None = None,
    icon: str | None = None,
    display_order: int = 0,
) -> db.Category:
    new_category = db.Category(
        name=name, description=description, icon=icon, display_order=display_order
    )
    session.add(new_category)
    session.commit()
    session.refresh(new_category)
    return new_category


def update_category(
    session: Session,
    category_id: str,
    name: str | None,
    description: str | None,
    icon: str | None = None,
    display_order: int | None = None,
) -> db.Category:
    category = session.query(db.Category).filter(db.Category.id == category_id).first()
    if not category:
        return None
    if name is not None:
        category.name = name
    if description is not None:
        category.description = description
    if icon is not None:
        category.icon = icon
    if display_order is not None:
        category.display_order = display_order
    session.commit()
    session.refresh(category)
    return category


def delete_category(session: Session, category_id: str) -> None:
    category = session.query(db.Category).filter(db.Category.id == category_id).first()
    if category:
        session.delete(category)
        session.commit()
