import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def get_org_variable_set(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> Optional[db.OrgVariableSet]:
    return (
        session.query(db.OrgVariableSet)
        .filter(
            db.OrgVariableSet.organization_id == organization_id,
            db.OrgVariableSet.set_id == set_id,
        )
        .first()
    )


def list_org_variable_sets(
    session: Session,
    organization_id: UUID,
) -> list[db.OrgVariableSet]:
    return (
        session.query(db.OrgVariableSet)
        .filter(db.OrgVariableSet.organization_id == organization_id)
        .order_by(db.OrgVariableSet.set_id)
        .all()
    )


def upsert_org_variable_set(
    session: Session,
    organization_id: UUID,
    set_id: str,
    values: dict[str, Any],
) -> db.OrgVariableSet:
    stmt = insert(db.OrgVariableSet).values(
        organization_id=organization_id,
        set_id=set_id,
        values=values,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["organization_id", "set_id"],
        set_={
            "values": stmt.excluded["values"],
            "updated_at": func.now(),
        },
    )
    stmt = stmt.returning(db.OrgVariableSet)
    result = session.execute(stmt)
    session.commit()
    instance = result.scalars().one()
    session.refresh(instance)
    return instance


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
