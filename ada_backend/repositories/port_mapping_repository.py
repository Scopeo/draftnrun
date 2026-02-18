from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def list_port_mappings_for_graph(session: Session, graph_runner_id: UUID) -> list[db.PortMapping]:
    return session.query(db.PortMapping).filter(db.PortMapping.graph_runner_id == graph_runner_id).all()


def delete_port_mappings_for_graph(session: Session, graph_runner_id: UUID) -> int:
    deleted = (
        session.query(db.PortMapping)
        .filter(db.PortMapping.graph_runner_id == graph_runner_id)
        .delete(synchronize_session=False)
    )
    session.commit()
    return deleted


def delete_port_mappings_involving_instance(
    session: Session,
    graph_runner_id: UUID,
    instance_id: UUID,
) -> int:
    """Delete all port mappings where the given instance is source or target."""
    deleted = (
        session.query(db.PortMapping)
        .filter(db.PortMapping.graph_runner_id == graph_runner_id)
        .filter(
            (db.PortMapping.source_instance_id == instance_id)
            | (db.PortMapping.target_instance_id == instance_id)
        )
        .delete(synchronize_session=False)
    )
    session.commit()
    return deleted


def delete_port_mappings_for_target_except(
    session: Session,
    graph_runner_id: UUID,
    target_instance_id: UUID,
    target_port_name: str,
    keep_source_instance_id: UUID,
    keep_source_port_name: str,
) -> int:
    q = (
        session.query(db.PortMapping)
        .filter(
            db.PortMapping.graph_runner_id == graph_runner_id,
            db.PortMapping.target_instance_id == target_instance_id,
            db.PortMapping.target_port_name == target_port_name,
        )
        .filter(
            (db.PortMapping.source_instance_id != keep_source_instance_id)
            | (db.PortMapping.source_port_name != keep_source_port_name)
        )
    )
    deleted = q.delete(synchronize_session=False)
    session.commit()
    return deleted


def get_output_port_definition_id(session: Session, component_version_id: UUID, port_name: str) -> UUID | None:
    """Get port definition ID for OUTPUT port, returns None if not found"""
    result = (
        session.query(db.PortDefinition.id)
        .filter_by(component_version_id=component_version_id, name=port_name, port_type=db.PortType.OUTPUT)
        .first()
    )
    return result[0] if result else None


def get_input_port_definition_id(session: Session, component_version_id: UUID, port_name: str) -> UUID | None:
    """Get port definition ID for INPUT port, returns None if not found"""
    result = (
        session.query(db.PortDefinition.id)
        .filter_by(component_version_id=component_version_id, name=port_name, port_type=db.PortType.INPUT)
        .first()
    )
    return result[0] if result else None


def get_port_definition_by_id(session: Session, port_def_id: UUID) -> db.PortDefinition | None:
    """Get port definition by ID, returns None if not found"""
    return session.query(db.PortDefinition).filter(db.PortDefinition.id == port_def_id).first()


def insert_port_mapping(
    session: Session,
    graph_runner_id: UUID,
    source_instance_id: UUID,
    source_port_definition_id: UUID,
    target_instance_id: UUID,
    target_port_definition_id: UUID,
    dispatch_strategy: str,
) -> db.PortMapping:
    mapping = db.PortMapping(
        graph_runner_id=graph_runner_id,
        source_instance_id=source_instance_id,
        source_port_definition_id=source_port_definition_id,
        target_instance_id=target_instance_id,
        target_port_definition_id=target_port_definition_id,
        dispatch_strategy=dispatch_strategy or "direct",
    )
    session.add(mapping)
    session.commit()
    return mapping


def delete_port_mapping_for_target_input(
    session: Session,
    graph_runner_id: UUID,
    target_instance_id: UUID,
    target_port_definition_id: UUID,
) -> int:
    """Delete existing port mappings for a specific target input (by ids)."""
    deleted = (
        session.query(db.PortMapping)
        .filter(
            db.PortMapping.graph_runner_id == graph_runner_id,
            db.PortMapping.target_instance_id == target_instance_id,
            db.PortMapping.target_port_definition_id == target_port_definition_id,
        )
        .delete(synchronize_session=False)
    )
    session.commit()
    return deleted
