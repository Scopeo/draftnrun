import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import (
    count_component_instances_by_version_id,
    count_component_versions_by_component_id,
    delete_component_by_id,
    delete_component_version_by_id,
    delete_release_stage_mapping,
    find_next_best_version_for_stage,
    get_component_version_by_id,
    get_release_stage_mapping,
    upsert_release_stage_mapping_core,
)
from ada_backend.services.errors import (
    ComponentNotFound,
    EntityInUseDeletionError,
    ComponentVersionMismatchError,
)

LOGGER = logging.getLogger(__name__)

# Stage order for determining downgrades (lower index = lower stage)
_STAGE_ORDER = [
    ReleaseStage.INTERNAL,
    ReleaseStage.BETA,
    ReleaseStage.EARLY_ACCESS,
    ReleaseStage.PUBLIC,
]


def update_component_version_release_stage_service(
    session: Session,
    component_id: UUID,
    component_version_id: UUID,
    release_stage: ReleaseStage,
) -> None:
    component_version = get_component_version_by_id(session, component_version_id)
    if component_version is None:
        raise ComponentNotFound(component_version_id)
    if component_version.component_id != component_id:
        LOGGER.warning(
            f"Component version {component_version_id} does not belong to "
            f"component {component_id}. Actual parent: {component_version.component_id}"
        )
        raise ComponentVersionMismatchError(
            component_version_id,
            expected_component_id=component_id,
            actual_component_id=component_version.component_id,
        )

    # Capture the old release stage before updating
    old_release_stage = component_version.release_stage

    # Update the version's release stage
    component_version.release_stage = release_stage
    session.add(component_version)

    # Update the mapping with replacement logic
    _update_release_stage_mapping_with_replacement(
        session,
        component_id,
        old_release_stage,
        release_stage,
        component_version_id,
    )

    session.commit()


def _update_release_stage_mapping_with_replacement(
    session: Session,
    component_id: UUID,
    old_release_stage: ReleaseStage,
    new_release_stage: ReleaseStage,
    component_version_id: UUID,
) -> None:
    """
    Updates the release stage mapping with replacement logic.
    If downgrading a version that was current for its old stage, finds and promotes
    the next best version for that stage, or removes the mapping if no suitable version exists.

    This is service layer logic that orchestrates repository calls.
    """
    # Get the old stage mapping to check if this version was current
    old_stage_mapping = get_release_stage_mapping(session, component_id, old_release_stage)
    was_current_for_old_stage = (
        old_stage_mapping is not None and old_stage_mapping.component_version_id == component_version_id
    )

    # Determine if this is a downgrade
    old_stage_index = _STAGE_ORDER.index(old_release_stage)
    new_stage_index = _STAGE_ORDER.index(new_release_stage)
    is_downgrade = new_stage_index < old_stage_index

    # Update the mapping for the new release stage
    upsert_release_stage_mapping_core(session, component_id, new_release_stage, component_version_id)

    # If downgrading and this version was current for the old stage, find a replacement
    if is_downgrade and was_current_for_old_stage:
        next_best_version = find_next_best_version_for_stage(
            session, component_id, old_release_stage, component_version_id
        )

        if next_best_version:
            LOGGER.info(
                f"Downgrading version {component_version_id} from {old_release_stage} to {new_release_stage}. "
                f"Promoting version {next_best_version.id} (stage: {next_best_version.release_stage}) "
                f"to be the new current version for {old_release_stage}."
            )
            upsert_release_stage_mapping_core(session, component_id, old_release_stage, next_best_version.id)
        elif old_stage_mapping:
            delete_release_stage_mapping(session, old_stage_mapping, commit=False)
            LOGGER.info(
                f"No suitable version found for {old_release_stage} stage for component {component_id}. "
                f"Removed {old_release_stage} mapping for downgraded version {component_version_id}."
            )


def delete_component_version_service(
    session: Session,
    component_id: UUID,
    component_version_id: UUID,
) -> None:
    component_version = get_component_version_by_id(session, component_version_id)
    if component_version is None:
        LOGGER.info(f"Component version {component_version_id} not found, treating as already deleted (idempotent)")
        return

    if component_version.component_id != component_id:
        LOGGER.warning(
            f"Component version {component_version_id} does not belong to component {component_id}. "
            f"Actual parent: {component_version.component_id}"
        )
        raise ComponentVersionMismatchError(
            component_version_id,
            expected_component_id=component_id,
            actual_component_id=component_version.component_id,
        )

    instance_count = count_component_instances_by_version_id(session, component_version_id)
    if instance_count > 0:
        LOGGER.warning(
            f"Cannot delete component version {component_version_id}: "
            f"it is currently used by {instance_count} instance(s)"
        )
        raise EntityInUseDeletionError(component_version_id, instance_count, entity_type="component version")

    version_count = count_component_versions_by_component_id(session, component_id)
    if version_count == 1:
        LOGGER.info(
            f"Component version {component_version_id} is the last version for "
            f"component {component_id}. "
            "Deleting the component directly (cascade will delete the version)."
        )
        delete_component_by_id(session, component_id)
    else:
        LOGGER.info(f"Deleting component version {component_version_id} from component {component_id}")
        delete_component_version_by_id(session, component_version_id)
