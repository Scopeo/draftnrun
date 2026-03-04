import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import SetType

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
    set_type: Optional[SetType] = None,
) -> list[db.OrgVariableSet]:
    query = session.query(db.OrgVariableSet).filter(db.OrgVariableSet.organization_id == organization_id)
    if set_type is not None:
        query = query.filter(db.OrgVariableSet.set_type == set_type)
    return query.order_by(db.OrgVariableSet.set_id).all()


def upsert_org_variable_set(
    session: Session,
    organization_id: UUID,
    set_id: str,
    values: dict[str, Any],
    set_type: SetType = SetType.VARIABLE,
    oauth_connection_id: Optional[UUID] = None,
) -> db.OrgVariableSet:
    stmt = insert(db.OrgVariableSet).values(
        organization_id=organization_id,
        set_id=set_id,
        values=values,
        set_type=set_type,
        oauth_connection_id=oauth_connection_id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["organization_id", "set_id"],
        set_={
            "values": stmt.excluded["values"],
            "set_type": stmt.excluded["set_type"],
            "oauth_connection_id": stmt.excluded["oauth_connection_id"],
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


def get_integration_set_by_connection_id(
    session: Session,
    organization_id: UUID,
    oauth_connection_id: UUID,
) -> Optional[db.OrgVariableSet]:
    return (
        session.query(db.OrgVariableSet)
        .filter(
            db.OrgVariableSet.organization_id == organization_id,
            db.OrgVariableSet.oauth_connection_id == oauth_connection_id,
            db.OrgVariableSet.set_type == SetType.INTEGRATION,
        )
        .first()
    )


def delete_integration_set_by_connection_id(
    session: Session,
    organization_id: UUID,
    oauth_connection_id: UUID,
) -> bool:
    variable_set = get_integration_set_by_connection_id(session, organization_id, oauth_connection_id)
    if not variable_set:
        LOGGER.debug(f"No integration set found for connection {oauth_connection_id} in org {organization_id}")
        return False
    session.delete(variable_set)
    session.commit()
    LOGGER.info(f"Deleted integration set {variable_set.set_id} for connection {oauth_connection_id}")
    return True
