from typing import Optional
from sqlalchemy.orm import Session
from uuid import UUID


from ada_backend.database import models as db


def _bump_patch(tag: Optional[str]) -> str:
    if not tag or not isinstance(tag, str):
        return "v0.0.1"

    try:
        version_parts = tag[1:].split(".")
        major, minor, patch = int(version_parts[0]), int(version_parts[1]), int(version_parts[2])

        new_patch = patch + 1
        # If patch goes over 99, bump minor and reset patch
        if new_patch > 99:
            new_minor = minor + 1
            new_patch = 0
            # If minor goes over 99, bump major and reset minor
            if new_minor > 99:
                major += 1
                new_minor = 0
            return f"v{major}.{new_minor}.{new_patch}"

        return f"v{major}.{minor}.{new_patch}"
    except (IndexError, ValueError):
        return "v0.0.1"


def get_graph_runner_tag_version(session: Session, graph_runner_id: UUID) -> Optional[str]:
    graph_runner = session.query(db.GraphRunner).filter(db.GraphRunner.id == graph_runner_id).first()
    return graph_runner.tag_version if graph_runner else None


def get_latest_tag_version_for_project(session: Session, project_id: UUID) -> Optional[str]:
    """Return the latest vX.Y.Z among this project's graph runners."""
    from sqlalchemy import func, cast, Integer

    # Extract major, minor, patch from tag_version and order by them
    result = (
        session.query(db.GraphRunner.tag_version)
        .join(
            db.ProjectEnvironmentBinding,
            db.ProjectEnvironmentBinding.graph_runner_id == db.GraphRunner.id,
        )
        .filter(db.ProjectEnvironmentBinding.project_id == project_id, db.GraphRunner.tag_version.isnot(None))
        .order_by(
            cast(func.split_part(func.substring(db.GraphRunner.tag_version, 2), ".", 1), Integer).desc(),
            cast(func.split_part(db.GraphRunner.tag_version, ".", 2), Integer).desc(),
            cast(func.split_part(db.GraphRunner.tag_version, ".", 3), Integer).desc(),
        )
        .first()
    )

    return result[0] if result else None


def compute_next_tag_version(session: Session, project_id: UUID) -> str:
    """Return the next tag for the project by bumping the latest patch (defaults to v0.0.1)."""
    latest = get_latest_tag_version_for_project(session, project_id)
    return _bump_patch(latest)


def update_graph_runner_tag_version(session: Session, graph_runner_id: UUID, new_tag: str) -> None:
    """Update the tag version for the specified graph runner."""
    graph_runner = session.query(db.GraphRunner).filter(db.GraphRunner.id == graph_runner_id).first()
    graph_runner.tag_version = new_tag
    session.add(graph_runner)
    session.commit()
