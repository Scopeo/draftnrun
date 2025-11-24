import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ReleaseStage

LOGGER = logging.getLogger(__name__)


STAGE_HIERARCHY = {
    ReleaseStage.INTERNAL: [ReleaseStage.INTERNAL, ReleaseStage.BETA, ReleaseStage.EARLY_ACCESS, ReleaseStage.PUBLIC],
    ReleaseStage.BETA: [ReleaseStage.BETA, ReleaseStage.EARLY_ACCESS, ReleaseStage.PUBLIC],
    ReleaseStage.EARLY_ACCESS: [ReleaseStage.EARLY_ACCESS, ReleaseStage.PUBLIC],
    ReleaseStage.PUBLIC: [ReleaseStage.PUBLIC],
}


def _build_stage_order() -> list[ReleaseStage]:
    """
    Builds the stage order from the stage hierarchy.
    Stages are ordered by the length of their accessible stages list
    (longest list = lowest stage, shortest list = highest stage).
    This ensures _STAGE_ORDER stays in sync with STAGE_HIERARCHY.
    """
    sorted_stages = sorted(STAGE_HIERARCHY.keys(), key=lambda stage: len(STAGE_HIERARCHY[stage]), reverse=True)
    return sorted_stages


_STAGE_ORDER = _build_stage_order()


def upsert_release_stage_mapping_core(
    session: Session,
    component_id: UUID,
    release_stage: ReleaseStage,
    component_version_id: UUID,
) -> None:
    """
    Core function that upserts a release stage mapping and removes higher stage mappings.
    This is the factorized logic used by both seeding and service updates.
    Does NOT commit the session - the caller is responsible for committing.

    Args:
        session: SQLAlchemy session
        component_id: ID of the component
        release_stage: The release stage (PUBLIC, BETA, EARLY_ACCESS, INTERNAL)
        component_version_id: ID of the component version to set as current for this stage
    """
    existing_mapping = (
        session.query(db.ReleaseStageToCurrentVersionMapping)
        .filter(
            db.ReleaseStageToCurrentVersionMapping.component_id == component_id,
            db.ReleaseStageToCurrentVersionMapping.release_stage == release_stage,
        )
        .first()
    )
    if existing_mapping:
        # Update the mapping to point to the specified version
        if existing_mapping.component_version_id != component_version_id:
            existing_mapping.component_version_id = component_version_id
            LOGGER.info(
                f"Updated release stage mapping for component {component_id} "
                f"stage {release_stage} to version {component_version_id}"
            )
        else:
            LOGGER.info(
                f"Release stage mapping for component {component_id} "
                f"stage {release_stage} already points to correct version, skipping."
            )
    else:
        # Create new mapping
        new_mapping = db.ReleaseStageToCurrentVersionMapping(
            component_id=component_id,
            release_stage=release_stage,
            component_version_id=component_version_id,
        )
        session.add(new_mapping)
        LOGGER.info(
            f"Created release stage mapping for component {component_id} "
            f"stage {release_stage} to version {component_version_id}"
        )

    target_stage_index = _STAGE_ORDER.index(release_stage)
    higher_stages = _STAGE_ORDER[target_stage_index + 1 :]
    if higher_stages:
        deleted_count = (
            session.query(db.ReleaseStageToCurrentVersionMapping)
            .filter(
                db.ReleaseStageToCurrentVersionMapping.component_id == component_id,
                db.ReleaseStageToCurrentVersionMapping.component_version_id == component_version_id,
                db.ReleaseStageToCurrentVersionMapping.release_stage.in_(higher_stages),
            )
            .delete(synchronize_session=False)
        )

        if deleted_count > 0:
            LOGGER.info(
                f"Removed {deleted_count} higher release stage mapping(s) for component {component_id} "
                f"version {component_version_id} (downgrade to {release_stage})"
            )


def find_next_best_version_for_stage(
    session: Session,
    component_id: UUID,
    old_release_stage: ReleaseStage,
    exclude_version_id: UUID,
) -> db.ComponentVersion | None:
    """
    Finds the next best version to become the current version for a given release stage.
    Looks for versions with the same or higher release stage, ordered by creation date (most recent first).

    Args:
        session: SQLAlchemy session
        component_id: ID of the component
        old_release_stage: The release stage that needs a replacement
        exclude_version_id: Version ID to exclude from the search

    Returns:
        The next best ComponentVersion, or None if no suitable version is found
    """
    old_stage_index = _STAGE_ORDER.index(old_release_stage)
    eligible_stages = _STAGE_ORDER[old_stage_index:]

    return (
        session.query(db.ComponentVersion)
        .filter(
            db.ComponentVersion.component_id == component_id,
            db.ComponentVersion.id != exclude_version_id,
            db.ComponentVersion.release_stage.in_(eligible_stages),
        )
        .order_by(db.ComponentVersion.created_at.desc())
        .first()
    )


def get_release_stage_mapping(
    session: Session,
    component_id: UUID,
    release_stage: ReleaseStage,
) -> db.ReleaseStageToCurrentVersionMapping | None:
    return (
        session.query(db.ReleaseStageToCurrentVersionMapping)
        .filter(
            db.ReleaseStageToCurrentVersionMapping.component_id == component_id,
            db.ReleaseStageToCurrentVersionMapping.release_stage == release_stage,
        )
        .first()
    )


def delete_release_stage_mapping(
    session: Session,
    mapping: db.ReleaseStageToCurrentVersionMapping,
    commit: bool = True,
) -> None:
    session.delete(mapping)
    if commit:
        session.commit()
