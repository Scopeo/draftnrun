import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def list_org_definitions(
    session: Session,
    organization_id: UUID,
) -> list[db.OrgVariableDefinition]:
    return (
        session.query(db.OrgVariableDefinition)
        .filter(db.OrgVariableDefinition.organization_id == organization_id)
        .order_by(db.OrgVariableDefinition.display_order, db.OrgVariableDefinition.name)
        .all()
    )


def get_org_definition(
    session: Session,
    organization_id: UUID,
    name: str,
) -> Optional[db.OrgVariableDefinition]:
    return (
        session.query(db.OrgVariableDefinition)
        .filter(
            db.OrgVariableDefinition.organization_id == organization_id,
            db.OrgVariableDefinition.name == name,
        )
        .first()
    )


def upsert_org_definition(
    session: Session,
    organization_id: UUID,
    name: str,
    **fields,
) -> db.OrgVariableDefinition:
    values = {
        "organization_id": organization_id,
        "name": name,
        **fields,
    }

    stmt = insert(db.OrgVariableDefinition).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_org_variable_definition",
        set_={
            "type": stmt.excluded.type,
            "description": stmt.excluded.description,
            "required": stmt.excluded.required,
            "default_value": stmt.excluded.default_value,
            "metadata": stmt.excluded.metadata,
            "editable": stmt.excluded.editable,
            "display_order": stmt.excluded.display_order,
            "updated_at": func.now(),
        },
    )
    stmt = stmt.returning(db.OrgVariableDefinition)
    result = session.execute(stmt)
    session.commit()
    instance = result.scalars().one()
    session.refresh(instance)
    return instance


def delete_org_definition(
    session: Session,
    organization_id: UUID,
    name: str,
) -> bool:
    definition = get_org_definition(session, organization_id, name)
    if not definition:
        return False
    session.delete(definition)
    session.commit()
    return True
