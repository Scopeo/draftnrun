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


def insert_port_mapping(
    session: Session,
    graph_runner_id: UUID,
    source_instance_id: UUID,
    source_port_name: str,
    target_instance_id: UUID,
    target_port_name: str,
    dispatch_strategy: str,
) -> db.PortMapping:
    mapping = db.PortMapping(
        graph_runner_id=graph_runner_id,
        source_instance_id=source_instance_id,
        source_port_name=source_port_name,
        target_instance_id=target_instance_id,
        target_port_name=target_port_name,
        dispatch_strategy=dispatch_strategy or "direct",
    )
    session.add(mapping)
    session.commit()
    return mapping
