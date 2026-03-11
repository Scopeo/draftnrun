import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import VariableType

LOGGER = logging.getLogger(__name__)


def list_org_definitions(
    session: Session,
    organization_id: UUID,
    project_id: Optional[UUID] = None,
    var_type: Optional[VariableType] = None,
) -> list[db.OrgVariableDefinition]:
    query = session.query(db.OrgVariableDefinition).filter(db.OrgVariableDefinition.organization_id == organization_id)

    if var_type is not None:
        query = query.filter(db.OrgVariableDefinition.type == var_type)

    if project_id is not None:
        query = query.outerjoin(
            db.OrgVariableDefinitionProjectAssociation,
            db.OrgVariableDefinition.id == db.OrgVariableDefinitionProjectAssociation.definition_id,
        ).filter(
            or_(
                db.OrgVariableDefinitionProjectAssociation.project_id == project_id,
                db.OrgVariableDefinitionProjectAssociation.id.is_(None),
            )
        )

    return query.order_by(db.OrgVariableDefinition.display_order, db.OrgVariableDefinition.name).all()


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
    instance = result.scalars().one()
    session.flush()
    session.refresh(instance)
    return instance


def replace_definition_projects(
    session: Session,
    definition_id: UUID,
    project_ids: list[UUID],
) -> None:
    session.query(db.OrgVariableDefinitionProjectAssociation).filter(
        db.OrgVariableDefinitionProjectAssociation.definition_id == definition_id
    ).delete()

    for project_id in project_ids:
        session.add(db.OrgVariableDefinitionProjectAssociation(definition_id=definition_id, project_id=project_id))

    session.flush()


def delete_org_definition(
    session: Session,
    organization_id: UUID,
    name: str,
) -> bool:
    definition = get_org_definition(session, organization_id, name)
    if not definition:
        return False
    session.delete(definition)
    return True


def get_oauth_definition_by_id(
    session: Session,
    definition_id: UUID,
) -> Optional[db.OrgVariableDefinition]:
    """Look up an oauth definition by ID. Used at runtime to resolve definition IDs to connection UUIDs."""
    return (
        session.query(db.OrgVariableDefinition)
        .filter(
            db.OrgVariableDefinition.id == definition_id,
            db.OrgVariableDefinition.type == VariableType.OAUTH,
        )
        .first()
    )


def find_oauth_definition_by_connection_id(
    session: Session,
    organization_id: UUID,
    connection_id: UUID,
) -> Optional[db.OrgVariableDefinition]:
    return (
        session.query(db.OrgVariableDefinition)
        .filter(
            db.OrgVariableDefinition.organization_id == organization_id,
            db.OrgVariableDefinition.type == VariableType.OAUTH,
            db.OrgVariableDefinition.variable_metadata["oauth_connection_id"].astext == str(connection_id),
        )
        .first()
    )


def delete_oauth_definitions_for_connection(
    session: Session,
    organization_id: UUID,
    connection_id: UUID,
) -> int:
    count = (
        session.query(db.OrgVariableDefinition)
        .filter(
            db.OrgVariableDefinition.organization_id == organization_id,
            db.OrgVariableDefinition.type == VariableType.OAUTH,
            db.OrgVariableDefinition.variable_metadata["oauth_connection_id"].astext == str(connection_id),
        )
        .delete(synchronize_session="fetch")
    )
    session.flush()
    return count
