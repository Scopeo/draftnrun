import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


# --- Project-scoped helpers (kept for backward compat) ---


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
        constraint="uq_org_variable_definition",
        set_={
            "project_id": stmt.excluded.project_id,
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


# --- Org-scoped definitions ---


def list_org_definitions(
    session: Session,
    organization_id: UUID,
) -> list[db.ProjectVariableDefinition]:
    return (
        session.query(db.ProjectVariableDefinition)
        .filter(db.ProjectVariableDefinition.organization_id == organization_id)
        .order_by(db.ProjectVariableDefinition.display_order, db.ProjectVariableDefinition.name)
        .all()
    )


def get_org_definition(
    session: Session,
    organization_id: UUID,
    name: str,
) -> Optional[db.ProjectVariableDefinition]:
    return (
        session.query(db.ProjectVariableDefinition)
        .filter(
            db.ProjectVariableDefinition.organization_id == organization_id,
            db.ProjectVariableDefinition.name == name,
        )
        .first()
    )


def upsert_org_definition(
    session: Session,
    organization_id: UUID,
    name: str,
    project_id: Optional[UUID] = None,
    **fields,
) -> db.ProjectVariableDefinition:
    values = {
        "organization_id": organization_id,
        "name": name,
        **fields,
    }
    if project_id is not None:
        values["project_id"] = project_id

    stmt = insert(db.ProjectVariableDefinition).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_org_variable_definition",
        set_={
            "project_id": stmt.excluded.project_id,
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

    return get_org_definition(session, organization_id, name)


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
