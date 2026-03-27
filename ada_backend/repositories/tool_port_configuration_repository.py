from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from ada_backend.database import models as db


class ToolPortConfigurationOwnershipError(ValueError):
    """Raised when a config id does not belong to the provided component instance."""


def get_tool_port_configurations(
    session: Session,
    component_instance_id: UUID,
    eager_load_port_definition: bool = False,
    eager_load_input_port_instance: bool = False,
) -> list[db.ToolPortConfiguration]:
    query = session.query(db.ToolPortConfiguration).filter(
        db.ToolPortConfiguration.component_instance_id == component_instance_id
    )
    if eager_load_port_definition:
        query = query.options(joinedload(db.ToolPortConfiguration.port_definition))
    if eager_load_input_port_instance:
        query = query.options(joinedload(db.ToolPortConfiguration.input_port_instance))
    return query.all()


def get_tool_port_configuration_by_id(
    session: Session,
    config_id: UUID,
) -> Optional[db.ToolPortConfiguration]:
    return (
        session.query(db.ToolPortConfiguration)
        .filter(db.ToolPortConfiguration.id == config_id)
        .first()
    )


def upsert_tool_port_configuration(
    session: Session,
    component_instance_id: UUID,
    setup_mode: db.PortSetupMode,
    port_definition_id: Optional[UUID] = None,
    input_port_instance_id: Optional[UUID] = None,
    ai_name_override: Optional[str] = None,
    ai_description_override: Optional[str] = None,
    is_required_override: Optional[bool] = None,
    custom_parameter_type: Optional[db.JsonSchemaType] = None,
    json_schema_override: Optional[dict] = None,
    expression_json: Optional[dict] = None,
    custom_ui_component_properties: Optional[dict] = None,
    id_: Optional[UUID] = None,
) -> db.ToolPortConfiguration:
    """Create or update a tool port configuration.

    If id_ is given, attempts to update the existing row.
    If port_definition_id is given, checks for an existing row on the same
    (component_instance_id, port_definition_id) pair before creating.
    If port_definition_id is NULL and ai_name_override is given, checks for an
    existing custom config on (component_instance_id, ai_name_override).

    This function does not commit the transaction; the caller manages commit/rollback.
    """
    existing: Optional[db.ToolPortConfiguration] = None

    if id_:
        existing = get_tool_port_configuration_by_id(session, id_)
        if existing and existing.component_instance_id != component_instance_id:
            raise ToolPortConfigurationOwnershipError(
                "ToolPortConfiguration id does not belong to the provided component_instance_id."
            )

    if not existing and port_definition_id:
        existing = (
            session.query(db.ToolPortConfiguration)
            .filter(
                db.ToolPortConfiguration.component_instance_id == component_instance_id,
                db.ToolPortConfiguration.port_definition_id == port_definition_id,
            )
            .first()
        )

    if not existing and port_definition_id is None and ai_name_override:
        existing = (
            session.query(db.ToolPortConfiguration)
            .filter(
                db.ToolPortConfiguration.component_instance_id == component_instance_id,
                db.ToolPortConfiguration.port_definition_id.is_(None),
                db.ToolPortConfiguration.ai_name_override == ai_name_override,
            )
            .first()
        )

    if existing:
        existing.setup_mode = setup_mode
        existing.ai_name_override = ai_name_override
        existing.ai_description_override = ai_description_override
        existing.is_required_override = is_required_override
        existing.custom_parameter_type = custom_parameter_type
        existing.json_schema_override = json_schema_override
        existing.expression_json = expression_json
        existing.custom_ui_component_properties = custom_ui_component_properties
        if input_port_instance_id is not None:
            existing.input_port_instance_id = input_port_instance_id
        session.add(existing)
    else:
        existing = db.ToolPortConfiguration(
            id=id_,
            component_instance_id=component_instance_id,
            port_definition_id=port_definition_id,
            input_port_instance_id=input_port_instance_id,
            setup_mode=setup_mode,
            ai_name_override=ai_name_override,
            ai_description_override=ai_description_override,
            is_required_override=is_required_override,
            custom_parameter_type=custom_parameter_type,
            json_schema_override=json_schema_override,
            expression_json=expression_json,
            custom_ui_component_properties=custom_ui_component_properties,
        )
        session.add(existing)

    session.flush()
    session.refresh(existing)
    return existing


def delete_tool_port_configurations_for_instance(
    session: Session,
    component_instance_id: UUID,
) -> int:
    """Delete all tool port configurations for a component instance.

    This function does not commit the transaction; the caller manages commit/rollback.
    """
    deleted = (
        session.query(db.ToolPortConfiguration)
        .filter(db.ToolPortConfiguration.component_instance_id == component_instance_id)
        .delete()
    )
    session.flush()
    return deleted
