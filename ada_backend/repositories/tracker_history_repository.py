from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EndpointIdTrackerHistory


def get_tracked_ids_history(session: Session, cron_id: UUID) -> list[EndpointIdTrackerHistory]:
    return (
        session.query(EndpointIdTrackerHistory)
        .filter(
            EndpointIdTrackerHistory.cron_id == cron_id,
        )
        .all()
    )


def create_tracked_id(
    session: Session, cron_id: UUID, tracked_id: str, organization_id: UUID, current_time: datetime
) -> None:
    new_record = EndpointIdTrackerHistory(
        cron_id=cron_id,
        organization_id=organization_id,
        tracked_id=str(tracked_id),
    )
    session.add(new_record)
    session.commit()


def delete_tracked_ids_history(session: Session, cron_id: UUID, tracked_ids: list[UUID]) -> None:
    session.query(EndpointIdTrackerHistory).filter(
        EndpointIdTrackerHistory.cron_id == cron_id,
        EndpointIdTrackerHistory.tracked_id.in_([str(rid) for rid in tracked_ids]),
    ).delete(synchronize_session=False)
    session.commit()
