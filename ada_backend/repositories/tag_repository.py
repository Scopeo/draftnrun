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
    results = (
        session.query(db.GraphRunner)
        .join(
            db.ProjectEnvironmentBinding,
            db.ProjectEnvironmentBinding.graph_runner_id == db.GraphRunner.id,
        )
        .filter(db.ProjectEnvironmentBinding.project_id == project_id)
        .all()
    )
    candidates: list[tuple[int, int, int]] = []
    for gr in results:
        if gr.tag_version:
            try:
                version_parts = gr.tag_version[1:].split(".")
                major, minor, patch = int(version_parts[0]), int(version_parts[1]), int(version_parts[2])
                candidates.append((major, minor, patch))
            except (IndexError, ValueError):
                continue
    if not candidates:
        return None
    latest = max(candidates)
    major, minor, patch = latest
    return f"v{major}.{minor}.{patch}"


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
