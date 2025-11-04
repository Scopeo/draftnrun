from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EndpointPollingHistory


def get_tracked_values_history(session: Session, cron_id: UUID) -> list[EndpointPollingHistory]:
    return (
        session.query(EndpointPollingHistory)
        .filter(
            EndpointPollingHistory.cron_id == cron_id,
        )
        .all()
    )


def create_tracked_value(
    session: Session, cron_id: UUID, tracked_value: str, organization_id: UUID, current_time: datetime
) -> None:
    new_record = EndpointPollingHistory(
        cron_id=cron_id,
        tracked_value=str(tracked_value),
    )
    session.add(new_record)
    session.commit()


def create_tracked_values_bulk(
    session: Session,
    cron_id: UUID,
    tracked_values: list[str],
) -> None:
    """Bulk insert tracked values in a single query."""
    if not tracked_values:
        return

    new_records = [
        EndpointPollingHistory(
            cron_id=cron_id,
            tracked_value=str(tracked_value),
        )
        for tracked_value in tracked_values
    ]
    session.bulk_save_objects(new_records)
    session.commit()


def delete_tracked_values_history(session: Session, cron_id: UUID, tracked_values: list[UUID]) -> None:
    session.query(EndpointPollingHistory).filter(
        EndpointPollingHistory.cron_id == cron_id,
        EndpointPollingHistory.tracked_value.in_([str(rid) for rid in tracked_values]),
    ).delete(synchronize_session=False)
    session.commit()
