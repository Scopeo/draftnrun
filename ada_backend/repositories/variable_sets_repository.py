import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def get_org_variable_set(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> Optional[db.ProjectVariableSet]:
    return (
        session.query(db.ProjectVariableSet)
        .filter(
            db.ProjectVariableSet.organization_id == organization_id,
            db.ProjectVariableSet.set_id == set_id,
        )
        .first()
    )


def list_org_variable_sets(
    session: Session,
    organization_id: UUID,
) -> list[db.ProjectVariableSet]:
    return (
        session.query(db.ProjectVariableSet)
        .filter(db.ProjectVariableSet.organization_id == organization_id)
        .order_by(db.ProjectVariableSet.set_id)
        .all()
    )


def upsert_org_variable_set(
    session: Session,
    organization_id: UUID,
    set_id: str,
    values: dict[str, Any],
) -> db.ProjectVariableSet:
    stmt = insert(db.ProjectVariableSet).values(
        organization_id=organization_id,
        set_id=set_id,
        values=values,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["organization_id", "set_id"],
        set_={
            "values": stmt.excluded["values"],
        },
    )
    session.execute(stmt)
    session.commit()

    return get_org_variable_set(session, organization_id, set_id)


def delete_org_variable_set(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> bool:
    variable_set = get_org_variable_set(session, organization_id, set_id)
    if not variable_set:
        return False
    session.delete(variable_set)
    session.commit()
    return True
