from typing import Optional

from sqlalchemy.orm import Session
from uuid import UUID

from ada_backend.repositories.tag_repository import get_latest_tag_version_for_project


def _bump_patch(tag: Optional[str]) -> str:
    if not tag or not isinstance(tag, str):
        return "0.0.1"

    try:
        version_parts = tag.split(".")
        major, minor, patch = int(version_parts[0]), int(version_parts[1]), int(version_parts[2])

        new_patch = patch + 1
        return f"{major}.{minor}.{new_patch}"
    except (IndexError, ValueError):
        return "0.0.1"


def compute_next_tag_version(session: Session, project_id: UUID) -> str:
    """Return the next tag for the project by bumping the latest patch (defaults to 0.0.1)."""
    latest = get_latest_tag_version_for_project(session, project_id)
    return _bump_patch(latest)


def compose_tag_name(tag_version: Optional[str], version_name: Optional[str]) -> Optional[str]:
    """Compose the tag name from tag_version and version_name, or return None if incomplete."""
    if tag_version and version_name:
        return f"{tag_version}-{version_name}"
    if tag_version:
        return tag_version
    return None
