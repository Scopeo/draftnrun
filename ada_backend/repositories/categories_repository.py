from typing import List

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def get_all_categories(session: Session) -> List[db.Category]:
    return session.query(db.Category).all()


def get_category_by_id(session: Session, category_id: str) -> db.Category:
    return session.query(db.Category).filter(db.Category.id == category_id).first()


def fetch_associated_category_names(session: Session, component_id: str) -> List[str]:
    """
    Retrieve categories associated with a component.

    Args:
        session (Session): SQLAlchemy session.
        component_id (str): ID of the component.

    Returns:
        List[str]: List of category names associated with the component.
    """
    categories = (
        session.query(db.Category.name)
        .join(db.ComponentCategory, db.ComponentCategory.category_id == db.Category.id)
        .filter(db.ComponentCategory.component_id == component_id)
        .all()
    )
    return [category.name for category in categories] if categories else []


def create_category(session: Session, name: str, description: str) -> db.Category:
    new_category = db.Category(name=name, description=description)
    session.add(new_category)
    session.commit()
    session.refresh(new_category)
    return new_category


def update_category(session: Session, category_id: str, name: str | None, description: str | None) -> db.Category:
    category = session.query(db.Category).filter(db.Category.id == category_id).first()
    if not category:
        return None
    if name is not None:
        category.name = name
    if description is not None:
        category.description = description
    session.commit()
    session.refresh(category)
    return category


def delete_category(session: Session, category_id: str) -> None:
    category = session.query(db.Category).filter(db.Category.id == category_id).first()
    if category:
        session.delete(category)
        session.commit()
