from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from ada_backend.database import models as db


def get_tool_input_configurations(
    session: Session, component_instance_id: UUID
) -> list[db.ToolInputConfiguration]:
    """Return all ToolInputConfigurations for a component instance."""
    return (
        session.query(db.ToolInputConfiguration)
        .join(db.InputPortInstance, db.ToolInputConfiguration.input_port_instance_id == db.InputPortInstance.id)
        .filter(db.InputPortInstance.component_instance_id == component_instance_id)
        .options(
            joinedload(db.ToolInputConfiguration.input_port_instance).joinedload(
                db.InputPortInstance.port_definition
            ),
            joinedload(db.ToolInputConfiguration.input_port_instance).joinedload(
                db.InputPortInstance.field_expression
            ),
        )
        .all()
    )


def get_tool_input_configuration_by_id(
    session: Session, config_id: UUID
) -> db.ToolInputConfiguration | None:
    return (
        session.query(db.ToolInputConfiguration)
        .filter(db.ToolInputConfiguration.id == config_id)
        .first()
    )


def get_tool_input_configuration_by_input_port_instance(
    session: Session, input_port_instance_id: UUID
) -> db.ToolInputConfiguration | None:
    return (
        session.query(db.ToolInputConfiguration)
        .filter(db.ToolInputConfiguration.input_port_instance_id == input_port_instance_id)
        .first()
    )


def insert_tool_input_configuration(
    session: Session,
    input_port_instance_id: UUID,
    setup_mode: db.PortSetupMode,
    ai_name_override: str | None = None,
    ai_description_override: str | None = None,
    is_required_override: bool | None = None,
    custom_parameter_type: str | None = None,
    json_schema_override: dict | None = None,
) -> db.ToolInputConfiguration:
    config = db.ToolInputConfiguration(
        input_port_instance_id=input_port_instance_id,
        setup_mode=setup_mode,
        ai_name_override=ai_name_override,
        ai_description_override=ai_description_override,
        is_required_override=is_required_override,
        custom_parameter_type=custom_parameter_type,
        json_schema_override=json_schema_override,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def update_tool_input_configuration(
    session: Session,
    config_id: UUID,
    setup_mode: db.PortSetupMode | None = None,
    ai_name_override: str | None = None,
    ai_description_override: str | None = None,
    is_required_override: bool | None = None,
    custom_parameter_type: str | None = None,
    json_schema_override: dict | None = None,
) -> db.ToolInputConfiguration | None:
    config = get_tool_input_configuration_by_id(session, config_id)
    if not config:
        return None

    if setup_mode is not None:
        config.setup_mode = setup_mode
    if ai_name_override is not None:
        config.ai_name_override = ai_name_override
    if ai_description_override is not None:
        config.ai_description_override = ai_description_override
    if is_required_override is not None:
        config.is_required_override = is_required_override
    if custom_parameter_type is not None:
        config.custom_parameter_type = custom_parameter_type
    if json_schema_override is not None:
        config.json_schema_override = json_schema_override

    session.commit()
    session.refresh(config)
    return config


def delete_tool_input_configuration(session: Session, config_id: UUID) -> bool:
    config = get_tool_input_configuration_by_id(session, config_id)
    if not config:
        return False
    session.delete(config)
    session.commit()
    return True


def upsert_tool_input_configurations(
    session: Session,
    component_instance_id: UUID,
    configs_list: list[dict],
) -> list[db.ToolInputConfiguration]:
    """Bulk upsert ToolInputConfigurations.

    Each item is identified by:
    1. ``id``: update the existing ToolInputConfiguration directly.
    2. ``input_port_instance_id``: look up existing config for that port instance, update or insert.

    Items without either key are skipped.
    """
    result_configs = []

    for config_data in configs_list:
        config_id = config_data.get("id")
        input_port_instance_id = config_data.get("input_port_instance_id")

        if config_id:
            config = update_tool_input_configuration(
                session=session,
                config_id=config_id,
                setup_mode=config_data.get("setup_mode"),
                ai_name_override=config_data.get("ai_name_override"),
                ai_description_override=config_data.get("ai_description_override"),
                is_required_override=config_data.get("is_required_override"),
                custom_parameter_type=config_data.get("custom_parameter_type"),
                json_schema_override=config_data.get("json_schema_override"),
            )
            if config:
                result_configs.append(config)

        elif input_port_instance_id:
            existing = get_tool_input_configuration_by_input_port_instance(session, input_port_instance_id)
            if existing:
                config = update_tool_input_configuration(
                    session=session,
                    config_id=existing.id,
                    setup_mode=config_data.get("setup_mode"),
                    ai_name_override=config_data.get("ai_name_override"),
                    ai_description_override=config_data.get("ai_description_override"),
                    is_required_override=config_data.get("is_required_override"),
                    custom_parameter_type=config_data.get("custom_parameter_type"),
                    json_schema_override=config_data.get("json_schema_override"),
                )
                if config:
                    result_configs.append(config)
            else:
                setup_mode = config_data.get("setup_mode")
                if setup_mode is None:
                    continue
                config = insert_tool_input_configuration(
                    session=session,
                    input_port_instance_id=input_port_instance_id,
                    setup_mode=setup_mode,
                    ai_name_override=config_data.get("ai_name_override"),
                    ai_description_override=config_data.get("ai_description_override"),
                    is_required_override=config_data.get("is_required_override"),
                    custom_parameter_type=config_data.get("custom_parameter_type"),
                    json_schema_override=config_data.get("json_schema_override"),
                )
                result_configs.append(config)

    return result_configs


# ---------------------------------------------------------------------------
# Backward-compatible aliases (keep callers working during transition)
# ---------------------------------------------------------------------------

get_port_configurations = get_tool_input_configurations
upsert_port_configurations = upsert_tool_input_configurations
