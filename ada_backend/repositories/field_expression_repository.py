from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def create_field_expression(
    session: Session,
    expression_json: dict,
) -> db.FieldExpression:
    expr = db.FieldExpression(
        expression_json=expression_json,
    )
    session.add(expr)
    session.commit()
    session.refresh(expr)
    return expr


def get_field_expression(
    session: Session,
    field_expression_id: UUID,
) -> Optional[db.FieldExpression]:
    return session.query(db.FieldExpression).filter(db.FieldExpression.id == field_expression_id).first()


def update_field_expression(
    session: Session,
    field_expression_id: UUID,
    expression_json: dict,
) -> Optional[db.FieldExpression]:
    expr = get_field_expression(session, field_expression_id)
    if not expr:
        return None

    expr.expression_json = expression_json
    session.add(expr)
    session.commit()
    session.refresh(expr)
    return expr


def delete_field_expression_by_id(
    session: Session,
    field_expression_id: UUID,
) -> bool:
    deleted_count = session.query(db.FieldExpression).filter(db.FieldExpression.id == field_expression_id).delete()
    if deleted_count > 0:
        session.commit()
        return True
    return False
