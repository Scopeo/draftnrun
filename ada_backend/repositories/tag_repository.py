import re
from typing import Optional
from sqlalchemy.orm import Session
from uuid import UUID

from ada_backend.database import models as db


SEMVER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _parse_version(tag: Optional[str]) -> Optional[tuple[int, int, int]]:
    if not tag or not isinstance(tag, str):
        return None
    m = SEMVER_RE.match(tag.strip())
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    except Exception:
        return None


def _to_tag(version_tuple: tuple[int, int, int]) -> str:
    major, minor, patch = version_tuple
    return f"v{major}.{minor}.{patch}"


def _bump_patch(tag: Optional[str]) -> str:
    parsed = _parse_version(tag)
    if parsed is None:
        return "v0.0.1"
    major, minor, patch = parsed
    return _to_tag((major, minor, patch + 1))


def get_graph_runner_tag_version(session: Session, graph_runner_id: UUID) -> str:
    graph_runner = session.query(db.GraphRunner).filter(db.GraphRunner.id == graph_runner_id).first()
    if not graph_runner:
        raise ValueError(f"Graph runner with ID {graph_runner_id} not found.")
    return graph_runner.tag_version


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
        parsed = _parse_version(gr.tag_version)
        if parsed is not None:
            candidates.append(parsed)
    if not candidates:
        return None
    latest = max(candidates)
    return _to_tag(latest)


def list_tag_versions(session: Session) -> list[str]:
    graph_runners = session.query(db.GraphRunner).all()
    tags: list[str] = []
    for gr in graph_runners:
        if isinstance(gr.tag_version, str):
            tags.append(gr.tag_version)
    return tags


def compute_next_tag_version(session: Session, project_id: UUID) -> str:
    """Return the next tag for the project by bumping the latest patch (defaults to v0.0.1)."""
    latest = get_latest_tag_version_for_project(session, project_id)
    return _bump_patch(latest)


def update_graph_runner_tag_version(session: Session, graph_runner_id: UUID, tag_version: str):
    graph_runner = session.query(db.GraphRunner).filter(db.GraphRunner.id == graph_runner_id).first()
    if not graph_runner:
        raise ValueError(f"Graph runner with ID {graph_runner_id} not found.")
    graph_runner.tag_version = tag_version
    session.add(graph_runner)
    session.commit()


def assign_next_tag_to_graph_runner(session: Session, graph_runner_id: UUID, project_id: UUID) -> str:
    """Compute next tag for the project and assign it to the specified graph runner. Returns the new tag."""
    new_tag = compute_next_tag_version(session, project_id)
    update_graph_runner_tag_version(session, graph_runner_id, new_tag)
    return new_tag
