from typing import List
from pytest import Session

from ada_backend.database import models as db


def get_categories(session: Session, component_id: str) -> List[str]:
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
