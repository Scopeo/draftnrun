from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from ada_backend.database import models as db


def upsert_field_expression(
    session: Session,
    component_instance_id: UUID,
    port_definition_id: UUID,
    expression_json: dict,
) -> db.FieldExpression:
    existing: Optional[db.FieldExpression] = (
        session.query(db.FieldExpression)
        .filter(
            db.FieldExpression.component_instance_id == component_instance_id,
            db.FieldExpression.port_definition_id == port_definition_id,
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
        port_definition_id=port_definition_id,
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
        .options(joinedload(db.FieldExpression.port_definition))
        .filter(db.FieldExpression.component_instance_id.in_(component_instance_ids))
        .all()
    )
