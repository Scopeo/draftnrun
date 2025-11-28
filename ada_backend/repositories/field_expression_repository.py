from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def upsert_field_expression(
    session: Session,
    component_instance_id: UUID,
    field_name: str,
    expression_json: dict,
) -> db.FieldExpression:
    existing: Optional[db.FieldExpression] = (
        session.query(db.FieldExpression)
        .filter(
            db.FieldExpression.component_instance_id == component_instance_id,
            db.FieldExpression.field_name == field_name,
        )
        .first()
    )

    if existing:
        existing.expression_json = expression_json
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    expr = db.FieldExpression(
        component_instance_id=component_instance_id,
        field_name=field_name,
        expression_json=expression_json,
    )
    session.add(expr)
    session.commit()
    session.refresh(expr)
    return expr


def get_field_expressions_for_instances(
    session: Session,
    component_instance_ids: list[UUID],
) -> list[db.FieldExpression]:
    return (
        session.query(db.FieldExpression)
        .filter(db.FieldExpression.component_instance_id.in_(component_instance_ids))
        .all()
    )


def delete_field_expressions_for_instance(
    session: Session,
    component_instance_id: UUID,
) -> None:
    """Delete all field expressions for a component instance"""
    session.query(db.FieldExpression).filter(
        db.FieldExpression.component_instance_id == component_instance_id
    ).delete()
    session.commit()


def delete_field_expression(
    session: Session,
    component_instance_id: UUID,
    field_name: str,
) -> None:
    """Delete a specific field expression for a component instance and field name"""
    deleted_count = (
        session.query(db.FieldExpression)
        .filter(
            db.FieldExpression.component_instance_id == component_instance_id,
            db.FieldExpression.field_name == field_name,
        )
        .delete()
    )
    if deleted_count > 0:
        session.commit()
