import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.component_definition_seeding import upsert_release_stage_to_current_version_mapping
from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import (
    count_component_instances_by_version_id,
    count_component_versions_by_component_id,
    delete_component_by_id,
    delete_component_version_by_id,
    get_component_version_by_id,
)
from ada_backend.services.errors import (
    ComponentNotFound,
    ComponentVersionInUseError,
    ComponentVersionMismatchError,
)

LOGGER = logging.getLogger(__name__)


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
            f"Component version {component_version_id} does not belong to component {component_id}. "
            f"Actual parent: {component_version.component_id}"
        )
        raise ComponentVersionMismatchError(
            component_version_id,
            expected_component_id=component_id,
            actual_component_id=component_version.component_id,
        )
    component_version.release_stage = release_stage
    session.add(component_version)
    upsert_release_stage_to_current_version_mapping(
        session, component_version.component_id, release_stage, component_version_id
    )
    session.commit()


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
        raise ComponentVersionInUseError(component_version_id, instance_count)

    version_count = count_component_versions_by_component_id(session, component_id)
    if version_count == 1:
        LOGGER.info(
            f"Component version {component_version_id} is the last version for component {component_id}. "
            "Deleting the component directly (cascade will delete the version)."
        )
        delete_component_by_id(session, component_id)
    else:
        LOGGER.info(f"Deleting component version {component_version_id} from component {component_id}")
        delete_component_version_by_id(session, component_version_id)
