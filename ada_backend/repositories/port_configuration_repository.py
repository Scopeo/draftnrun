import uuid
from uuid import UUID

from sqlalchemy.orm import Session, joinedload, with_polymorphic

from ada_backend.database import models as db
from ada_backend.repositories import field_expression_repository


def get_port_configurations(session: Session, component_instance_id: UUID) -> list[db.PortConfiguration]:
    poly = with_polymorphic(db.PortConfiguration, [db.ToolInputConfiguration])

    return (
        session.query(poly)
        .outerjoin(db.PortDefinition, poly.port_definition_id == db.PortDefinition.id)
        .options(
            joinedload(poly.port_definition),
            joinedload(poly.field_expression),
        )
        .filter(poly.component_instance_id == component_instance_id)
        .all()
    )


def get_port_configuration_by_id(session: Session, config_id: UUID) -> db.PortConfiguration | None:
    return session.query(db.PortConfiguration).filter(db.PortConfiguration.id == config_id).first()


def get_port_configuration_by_port_definition(
    session: Session, component_instance_id: UUID, port_definition_id: UUID
) -> db.PortConfiguration | None:
    return (
        session.query(db.PortConfiguration)
        .filter(
            db.PortConfiguration.component_instance_id == component_instance_id,
            db.PortConfiguration.port_definition_id == port_definition_id,
        )
        .first()
    )


def get_port_configuration_by_custom_name(
    session: Session, component_instance_id: UUID, custom_port_name: str
) -> db.ToolInputConfiguration | None:
    return (
        session.query(db.ToolInputConfiguration)
        .filter(
            db.ToolInputConfiguration.component_instance_id == component_instance_id,
            db.ToolInputConfiguration.custom_port_name == custom_port_name,
        )
        .first()
    )


def insert_port_configuration(
    session: Session,
    component_instance_id: UUID,
    setup_mode: db.PortSetupMode,
    port_definition_id: UUID | None = None,
    field_expression_id: UUID | None = None,
    expression_json: dict | None = None,
    ai_name_override: str | None = None,
    ai_description_override: str | None = None,
    is_required_override: bool | None = None,
    custom_port_name: str | None = None,
    custom_port_description: str | None = None,
    custom_parameter_type: str | None = None,
    custom_ui_component_properties: dict | None = None,
    json_schema_override: dict | None = None,
) -> db.ToolInputConfiguration:
    if expression_json and not field_expression_id:
        if port_definition_id:
            field_name = f"port_config_{port_definition_id}"
        elif custom_port_name:
            field_name = custom_port_name
        else:
            field_name = f"port_config_{uuid.uuid4()}"

        field_expr = field_expression_repository.upsert_field_expression(
            session=session,
            component_instance_id=component_instance_id,
            field_name=field_name,
            expression_json=expression_json,
        )
        field_expression_id = field_expr.id

    config = db.ToolInputConfiguration(
        component_instance_id=component_instance_id,
        port_definition_id=port_definition_id,
        setup_mode=setup_mode,
        field_expression_id=field_expression_id,
        ai_name_override=ai_name_override,
        ai_description_override=ai_description_override,
        is_required_override=is_required_override,
        custom_port_name=custom_port_name,
        custom_port_description=custom_port_description,
        custom_parameter_type=custom_parameter_type,
        custom_ui_component_properties=custom_ui_component_properties,
        json_schema_override=json_schema_override,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def update_port_configuration(
    session: Session,
    config_id: UUID,
    setup_mode: db.PortSetupMode | None = None,
    field_expression_id: UUID | None = None,
    expression_json: dict | None = None,
    ai_name_override: str | None = None,
    ai_description_override: str | None = None,
    is_required_override: bool | None = None,
    custom_port_name: str | None = None,
    custom_port_description: str | None = None,
    custom_parameter_type: str | None = None,
    custom_ui_component_properties: dict | None = None,
    json_schema_override: dict | None = None,
) -> db.PortConfiguration | None:
    config = get_port_configuration_by_id(session, config_id)
    if not config:
        return None

    # setup_mode is only on ToolInputConfiguration
    if setup_mode is not None and isinstance(config, db.ToolInputConfiguration):
        config.setup_mode = setup_mode

    # Handle field expression updates
    if expression_json is not None:
        if config.field_expression_id:
            # Update existing field expression
            field_expr = (
                session.query(db.FieldExpression).filter(db.FieldExpression.id == config.field_expression_id).first()
            )
            if field_expr:
                field_expr.expression_json = expression_json
        else:
            if config.port_definition_id:
                field_name = f"port_config_{config.port_definition_id}"
            elif config.custom_port_name:
                field_name = config.custom_port_name
            else:
                field_name = f"port_config_{config.id}"

            field_expr = field_expression_repository.upsert_field_expression(
                session=session,
                component_instance_id=config.component_instance_id,
                field_name=field_name,
                expression_json=expression_json,
            )
            config.field_expression_id = field_expr.id
    elif field_expression_id is not None:
        config.field_expression_id = field_expression_id

    # These fields are only on ToolInputConfiguration
    if isinstance(config, db.ToolInputConfiguration):
        if ai_name_override is not None:
            config.ai_name_override = ai_name_override
        if ai_description_override is not None:
            config.ai_description_override = ai_description_override
        if is_required_override is not None:
            config.is_required_override = is_required_override
        if custom_port_name is not None:
            config.custom_port_name = custom_port_name
        if custom_port_description is not None:
            config.custom_port_description = custom_port_description
        if custom_parameter_type is not None:
            config.custom_parameter_type = custom_parameter_type
        if custom_ui_component_properties is not None:
            config.custom_ui_component_properties = custom_ui_component_properties
        if json_schema_override is not None:
            config.json_schema_override = json_schema_override

    session.commit()
    session.refresh(config)
    return config


def delete_port_configuration(session: Session, config_id: UUID) -> bool:
    config = get_port_configuration_by_id(session, config_id)
    if not config:
        return False

    session.delete(config)
    session.commit()
    return True


def upsert_port_configurations(
    session: Session,
    component_instance_id: UUID,
    configs_list: list[dict],
) -> list[db.PortConfiguration]:
    result_configs = []

    for config_data in configs_list:
        config_id = config_data.get("id")
        port_definition_id = config_data.get("parameter_id")
        custom_port_name = config_data.get("custom_port_name")

        if config_id:
            config = update_port_configuration(
                session=session,
                config_id=config_id,
                setup_mode=config_data.get("setup_mode"),
                field_expression_id=config_data.get("field_expression_id"),
                expression_json=config_data.get("expression_json"),
                ai_name_override=config_data.get("ai_name_override"),
                ai_description_override=config_data.get("ai_description_override"),
                is_required_override=config_data.get("is_required_override"),
                custom_port_name=config_data.get("custom_port_name"),
                custom_port_description=config_data.get("custom_port_description"),
                custom_parameter_type=config_data.get("custom_parameter_type"),
                custom_ui_component_properties=config_data.get("custom_ui_component_properties"),
                json_schema_override=config_data.get("json_schema_override"),
            )
            if config:
                result_configs.append(config)
        else:
            existing_config = None
            if port_definition_id:
                existing_config = get_port_configuration_by_port_definition(
                    session, component_instance_id, port_definition_id
                )
            elif custom_port_name:
                existing_config = get_port_configuration_by_custom_name(
                    session, component_instance_id, custom_port_name
                )

            if existing_config:
                config = update_port_configuration(
                    session=session,
                    config_id=existing_config.id,
                    setup_mode=config_data.get("setup_mode"),
                    field_expression_id=config_data.get("field_expression_id"),
                    expression_json=config_data.get("expression_json"),
                    ai_name_override=config_data.get("ai_name_override"),
                    ai_description_override=config_data.get("ai_description_override"),
                    is_required_override=config_data.get("is_required_override"),
                    custom_port_name=config_data.get("custom_port_name"),
                    custom_port_description=config_data.get("custom_port_description"),
                    custom_parameter_type=config_data.get("custom_parameter_type"),
                    custom_ui_component_properties=config_data.get("custom_ui_component_properties"),
                    json_schema_override=config_data.get("json_schema_override"),
                )
                if config:
                    result_configs.append(config)
            else:
                config = insert_port_configuration(
                    session=session,
                    component_instance_id=component_instance_id,
                    port_definition_id=port_definition_id,
                    setup_mode=config_data["setup_mode"],
                    field_expression_id=config_data.get("field_expression_id"),
                    expression_json=config_data.get("expression_json"),
                    ai_name_override=config_data.get("ai_name_override"),
                    ai_description_override=config_data.get("ai_description_override"),
                    is_required_override=config_data.get("is_required_override"),
                    custom_port_name=custom_port_name,
                    custom_port_description=config_data.get("custom_port_description"),
                    custom_parameter_type=config_data.get("custom_parameter_type"),
                    custom_ui_component_properties=config_data.get("custom_ui_component_properties"),
                    json_schema_override=config_data.get("json_schema_override"),
                )
                result_configs.append(config)

    return result_configs
