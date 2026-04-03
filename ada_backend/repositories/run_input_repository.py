from typing import Optional
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ada_backend.database.models import RunInput


def save_run_input(
    session: Session,
    retry_group_id: UUID,
    project_id: UUID,
    input_data: dict,
) -> None:
    """Persist run input for retries."""
    stmt = (
        pg_insert(RunInput)
        .values(
            retry_group_id=retry_group_id,
            project_id=project_id,
            input_data=input_data,
        )
        .on_conflict_do_nothing(index_elements=["retry_group_id"])
    )
    session.execute(stmt)

    session.commit()


def get_run_input(session: Session, retry_group_id: UUID) -> Optional[dict]:
    row = session.query(RunInput).filter(RunInput.retry_group_id == retry_group_id).first()
    if row is None:
        return None
    return row.input_data
