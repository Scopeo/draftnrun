import logging
import uuid
from typing import Optional
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def get_project_option(
    session: Session,
    project_id: UUID,
    option_key: str,
) -> Optional[db.ProjectOption]:
    return (
        session.query(db.ProjectOption)
        .filter(
            db.ProjectOption.project_id == project_id,
            db.ProjectOption.option_key == option_key,
        )
        .first()
    )


def list_project_options(
    session: Session,
    project_id: UUID,
) -> list[db.ProjectOption]:
    return (
        session.query(db.ProjectOption)
        .filter(db.ProjectOption.project_id == project_id)
        .order_by(db.ProjectOption.created_at.desc())
        .all()
    )


def upsert_project_option(
    session: Session,
    project_id: UUID,
    option_key: str,
    options: dict,
) -> db.ProjectOption:
    stmt = insert(db.ProjectOption).values(
        id=uuid.uuid4(),
        project_id=project_id,
        option_key=option_key,
        options=options,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_project_option_key",
        set_={"options": options},
    )
    session.execute(stmt)
    session.commit()

    result = get_project_option(session, project_id, option_key)
    return result


def delete_project_option(
    session: Session,
    project_id: UUID,
    option_key: str,
) -> bool:
    existing = get_project_option(session, project_id, option_key)
    if not existing:
        return False
    session.delete(existing)
    session.commit()
    return True
