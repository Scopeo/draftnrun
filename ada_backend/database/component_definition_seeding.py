import logging

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
                f"Component parameter child relationship {component_parameter_child_relationship.id} updated."

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
