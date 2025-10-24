import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.utils import update_model_fields, models_are_equal


LOGGER = logging.getLogger(__name__)


def upsert_components(
    session: Session,
    components: list[db.Component],
) -> None:
    """
    Upserts a list of components into the database.
    If a component with the same ID exists and has different attributes, it will be updated.
    If it exists and has the same attributes, it will be skipped.
    If a component with the same ID does not exist, it will be inserted.
    """
    for component in components:
        existing_component = (
            session.query(db.Component)
            .filter(
                db.Component.id == component.id,
            )
            .first()
        )

        if existing_component:
            if models_are_equal(existing_component, component):
                LOGGER.info(f"Component {component.name} did not change, skipping.")
            else:
                update_model_fields(existing_component, component)
                LOGGER.info(f"Component {component.name} updated.")
        else:
            session.add(component)
            LOGGER.info(f"Component {component.name} inserted.")
    session.commit()


def upsert_component_versions(
    session: Session,
    component_versions: list[db.ComponentVersion],
) -> None:
    """
    Upserts component versions in the database.
    If a component version already exists and has same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.

    Note: This function does NOT automatically create release stage mappings.
    Use upsert_release_stage_to_current_version_mapping() to manually specify
    which version should be current for each release stage.
    """
    for component_version in component_versions:
        existing_component_version = (
            session.query(db.ComponentVersion)
            .filter(
                db.ComponentVersion.id == component_version.id,
            )
            .first()
        )
        if existing_component_version:
            component_version.release_stage = existing_component_version.release_stage
        else:
            if getattr(component_version, "release_stage", None) is None:
                component_version.release_stage = db.ReleaseStage.INTERNAL

        if existing_component_version:
            if models_are_equal(existing_component_version, component_version):
                LOGGER.info(f"Component version {component_version.id} did not change, skipping.")
            else:
                update_model_fields(existing_component_version, component_version)
                LOGGER.info(f"Component version {component_version.id} updated.")
        else:
            session.add(component_version)
            LOGGER.info(f"Component version {component_version.id} inserted.")
    session.commit()


def upsert_components_parameter_definitions(
    session: Session,
    component_parameter_definitions: list[db.ComponentParameterDefinition],
):
    """
    Upserts component parameter definitions in the database.
    If a component parameter definition already exists and has same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """
    for component_parameter_definition in component_parameter_definitions:
        existing_parameter_definition = (
            session.query(db.ComponentParameterDefinition)
            .filter(
                db.ComponentParameterDefinition.id == component_parameter_definition.id,
            )
            .first()
        )
        if existing_parameter_definition:
            if models_are_equal(existing_parameter_definition, component_parameter_definition):
                LOGGER.info(
                    f"Component parameter definition {component_parameter_definition.name} did not change, skipping."
                )
            else:
                update_model_fields(existing_parameter_definition, component_parameter_definition)
                LOGGER.info(f"Component parameter definition {component_parameter_definition.name} updated.")

        else:
            session.add(component_parameter_definition)
            LOGGER.info(f"Component parameter definition {component_parameter_definition.name} inserted.")
    session.commit()


def upsert_components_parameter_child_relationships(
    session: Session,
    component_parameter_child_relationships: list[db.ComponentParameterChildRelationship],
):
    """
    Upserts component parameter child relationships in the database.
    If a component parameter child relationship already exists and has same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """

    for component_parameter_child_relationship in component_parameter_child_relationships:
        existing_relationship = (
            session.query(db.ComponentParameterChildRelationship)
            .filter(
                db.ComponentParameterChildRelationship.id == component_parameter_child_relationship.id,
            )
            .first()
        )
        if existing_relationship:
            if models_are_equal(existing_relationship, component_parameter_child_relationship):
                LOGGER.info(
                    f"Component parameter child relationship {component_parameter_child_relationship.id} "
                    "did not change, skipping."
                )
            else:
                update_model_fields(existing_relationship, component_parameter_child_relationship)
                LOGGER.info(
                    f"Component parameter child relationship {component_parameter_child_relationship.id} updated."
                )

        else:
            session.add(component_parameter_child_relationship)
            LOGGER.info(
                f"Component parameter child relationship {component_parameter_child_relationship.id} inserted."
            )
    session.commit()


def upsert_tool_descriptions(
    session: Session,
    tool_descriptions: list[db.ToolDescription],
) -> None:
    """
    Upserts tool descriptions in the database.
    If a tool description already exists and has same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """
    for tool_description in tool_descriptions:
        existing_tool_description = (
            session.query(db.ToolDescription)
            .filter(
                db.ToolDescription.id == tool_description.id,
            )
            .first()
        )
        if existing_tool_description:
            if models_are_equal(existing_tool_description, tool_description):
                LOGGER.info(f"Tool description {tool_description.name} did not change, skipping.")
            else:
                update_model_fields(existing_tool_description, tool_description)
                LOGGER.info(f"Tool description {tool_description.name} updated.")
        else:
            session.add(tool_description)
            LOGGER.info(f"Tool description {tool_description.name} inserted.")
    session.commit()


def upsert_integrations(session: Session, integrations: list[db.Integration]) -> None:
    """
    Upserts integrations in the database.
    If an integration already exists and has same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """
    for integration in integrations:
        existing_integration = (
            session.query(db.Integration)
            .filter(
                db.Integration.id == integration.id,
            )
            .first()
        )
        if existing_integration:
            if models_are_equal(existing_integration, integration):
                LOGGER.info(f"Integration {integration.name} did not change, skipping.")
            else:
                update_model_fields(existing_integration, integration)
                LOGGER.info(f"Integration {integration.name} updated.")
        else:
            session.add(integration)
            LOGGER.info(f"Integration {integration.name} inserted.")
    session.commit()


def upsert_categories(
    session: Session,
    categories: list[db.Category],
) -> None:
    """
    Upserts categories in the database.
    If a category already exists and has same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """
    for category in categories:
        existing_category = (
            session.query(db.Category)
            .filter(
                db.Category.id == category.id,
            )
            .first()
        )
        if existing_category:
            if models_are_equal(existing_category, category):
                LOGGER.info(f"Category {category.name} did not change, skipping.")
            else:
                update_model_fields(existing_category, category)
                LOGGER.info(f"Category {category.name} updated.")
        else:
            session.add(category)
            LOGGER.info(f"Category {category.name} inserted.")
    session.commit()


def upsert_release_stage_to_current_version_mapping(
    session: Session,
    component_id: UUID,
    release_stage: db.ReleaseStage,
    component_version_id: UUID,
) -> None:
    """
    Upserts a single release stage to current version mapping in the database.
    This allows manual control over which component version is considered "current"
    for a specific release stage. This is required for get_current_component_versions to work properly.
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
    stage_order = [
        db.ReleaseStage.INTERNAL,
        db.ReleaseStage.BETA,
        db.ReleaseStage.EARLY_ACCESS,
        db.ReleaseStage.PUBLIC,
    ]
    target_stage_index = stage_order.index(release_stage)

    higher_stages = stage_order[target_stage_index + 1 :]
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
    session.commit()


def upsert_component_categories(session: Session, component_id: str, category_ids: list[UUID]) -> None:
    """
    Upserts component categories in the database.
    If a component category already exists and has same attributes, it will be skipped.
    If it exists but has different attributes, it will be updated.
    If it does not exist, it will be inserted.
    """
    existing_component_categories = (
        session.query(db.ComponentCategory)
        .filter(
            db.ComponentCategory.component_id == component_id,
        )
        .all()
    )
    existing_categories_set = set(
        existing_component_category.category_id for existing_component_category in existing_component_categories
    )
    category_ids_to_remove = existing_categories_set - set(category_ids)
    for category_id in category_ids_to_remove:
        component_category = (
            session.query(db.ComponentCategory)
            .filter(
                db.ComponentCategory.component_id == component_id,
                db.ComponentCategory.category_id == category_id,
            )
            .first()
        )
        session.delete(component_category)
        category_name = session.query(db.Category).filter(db.Category.id == category_id).first().name
        LOGGER.info(f"Component {component_id} removed from category {category_name}.")

    new_category_ids = set(category_ids) - existing_categories_set
    if not new_category_ids:
        LOGGER.info(f"Component {component_id} already has all categories, skipping.")
        return

    for category_id in new_category_ids:
        category = session.query(db.Category).filter(db.Category.id == category_id).first()
        if category:
            new_component_category = db.ComponentCategory(component_id=component_id, category=category)
            session.add(new_component_category)
            LOGGER.info(f"Component {component_id} added to category {category.name}.")

    session.commit()
