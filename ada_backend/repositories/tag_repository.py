from typing import Optional
from sqlalchemy.orm import Session
from uuid import UUID
from sqlalchemy import func, cast, Integer

from ada_backend.database import models as db


def get_latest_tag_version_for_project(session: Session, project_id: UUID) -> Optional[str]:
    """Return the latest X.Y.Z among this project's graph runners."""
    result = (
        session.query(db.GraphRunner.tag_version)
        .join(
            db.ProjectEnvironmentBinding,
            db.ProjectEnvironmentBinding.graph_runner_id == db.GraphRunner.id,
        )
        .filter(db.ProjectEnvironmentBinding.project_id == project_id, db.GraphRunner.tag_version.isnot(None))
        .order_by(
            cast(func.split_part(db.GraphRunner.tag_version, ".", 1), Integer).desc(),
            cast(func.split_part(db.GraphRunner.tag_version, ".", 2), Integer).desc(),
            cast(func.split_part(db.GraphRunner.tag_version, ".", 3), Integer).desc(),
        )
        .first()
    )

    return result[0] if result else None


def update_graph_runner_tag_version(session: Session, graph_runner_id: UUID, new_tag: str) -> None:
    """Update the tag version for the specified graph runner."""
    graph_runner = session.query(db.GraphRunner).filter(db.GraphRunner.id == graph_runner_id).first()
    graph_runner.tag_version = new_tag
    session.add(graph_runner)
    session.commit()


def update_graph_runner_tag_fields(
    session: Session,
    graph_runner_id: UUID,
    *,
    tag_version: Optional[str] = None,
    version_name: Optional[str] = None,
    change_log: Optional[str] = None,
) -> None:
    """Update GraphRunner tag-related fields in one place.

    Any parameter left as None will keep its current value.
    """
    graph_runner = session.query(db.GraphRunner).filter(db.GraphRunner.id == graph_runner_id).first()
    if not graph_runner:
        return

    if tag_version is not None:
        graph_runner.tag_version = tag_version
    if version_name is not None:
        graph_runner.version_name = version_name
    if change_log is not None:
        graph_runner.change_log = change_log

    session.add(graph_runner)
    session.commit()
