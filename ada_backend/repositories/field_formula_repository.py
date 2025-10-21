from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def upsert_field_formula(
    session: Session,
    component_instance_id: UUID,
    field_name: str,
    formula_json: dict,
) -> db.FieldFormula:
    existing: Optional[db.FieldFormula] = (
        session.query(db.FieldFormula)
        .filter(
            db.FieldFormula.component_instance_id == component_instance_id,
            db.FieldFormula.field_name == field_name,
        )
        .first()
    )

    if existing:
        existing.formula_json = formula_json
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    expr = db.FieldFormula(
        component_instance_id=component_instance_id,
        field_name=field_name,
        formula_json=formula_json,
    )
    session.add(expr)
    session.commit()
    session.refresh(expr)
    return expr


def get_field_formulas_for_instances(
    session: Session,
    component_instance_ids: list[UUID],
) -> list[db.FieldFormula]:
    if not component_instance_ids:
        return []
    return (
        session.query(db.FieldFormula)
        .filter(db.FieldFormula.component_instance_id.in_(component_instance_ids))
        .all()
    )
