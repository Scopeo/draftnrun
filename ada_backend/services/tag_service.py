from typing import Optional

from sqlalchemy.orm import Session
from uuid import UUID

from ada_backend.repositories.tag_repository import get_latest_tag_version_for_project


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


def compute_next_tag_version(session: Session, project_id: UUID) -> str:
    """Return the next tag for the project by bumping the latest patch (defaults to v0.0.1)."""
    latest = get_latest_tag_version_for_project(session, project_id)
    return _bump_patch(latest)
