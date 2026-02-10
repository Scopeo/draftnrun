import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def list_definitions(
    session: Session,
    project_id: UUID,
) -> list[db.ProjectVariableDefinition]:
    return (
        session.query(db.ProjectVariableDefinition)
        .filter(db.ProjectVariableDefinition.project_id == project_id)
        .order_by(db.ProjectVariableDefinition.display_order, db.ProjectVariableDefinition.name)
        .all()
    )


def get_definition(
    session: Session,
    project_id: UUID,
    name: str,
) -> Optional[db.ProjectVariableDefinition]:
    return (
        session.query(db.ProjectVariableDefinition)
        .filter(
            db.ProjectVariableDefinition.project_id == project_id,
            db.ProjectVariableDefinition.name == name,
        )
        .first()
    )


def upsert_definition(
    session: Session,
    project_id: UUID,
    name: str,
    **fields,
) -> db.ProjectVariableDefinition:
    stmt = insert(db.ProjectVariableDefinition).values(
        project_id=project_id,
        name=name,
        **fields,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_project_variable_definition",
        set_={
            "type": stmt.excluded.type,
            "description": stmt.excluded.description,
            "required": stmt.excluded.required,
            "default_value": stmt.excluded.default_value,
            "metadata": stmt.excluded.metadata,
            "editable": stmt.excluded.editable,
            "display_order": stmt.excluded.display_order,
        },
    )
    session.execute(stmt)
    session.commit()

    definition = get_definition(session, project_id, name)
    return definition


def bulk_upsert_definitions(
    session: Session,
    project_id: UUID,
    definitions: list[dict],
) -> list[db.ProjectVariableDefinition]:
    for defn in definitions:
        defn = dict(defn)  # avoid mutating caller's dict
        name = defn.pop("name")
        upsert_definition(session, project_id, name, **defn)

    return list_definitions(session, project_id)


def delete_definition(
    session: Session,
    project_id: UUID,
    name: str,
) -> bool:
    definition = get_definition(session, project_id, name)
    if not definition:
        return False
    session.delete(definition)
    session.commit()
    return True
