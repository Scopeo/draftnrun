"""Tests for OutputPortInstance lifecycle and cascade behaviors.

Verifies what happens at the DB level when a component instance with dynamic
output ports is involved:

- Deleting a ComponentInstance cascade-deletes its OutputPortInstances.
- Deleting the source ComponentInstance cascade-deletes PortMappings that reference it.
- Deleting an OutputPortInstance individually sets PortMapping.source_output_port_instance_id
  to NULL, leaving a dangling mapping that get_source_port_name() resolves to None.
- delete_output_port_instances_for_component_instance only touches OUTPUT ports,
  leaving INPUT port instances on the same component untouched.
"""

import uuid

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories import output_port_instance_repository
from ada_backend.repositories.port_mapping_repository import get_source_port_name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component_instance(session) -> db.ComponentInstance:
    component = db.Component(id=uuid.uuid4(), name=f"Comp-{uuid.uuid4()}")
    session.add(component)
    session.flush()

    version = db.ComponentVersion(id=uuid.uuid4(), component_id=component.id, version_tag="1.0.0")
    session.add(version)
    session.flush()

    instance = db.ComponentInstance(id=uuid.uuid4(), component_version_id=version.id, name="Instance")
    session.add(instance)
    session.commit()
    return instance


def _make_input_port_definition(session, component_version_id: uuid.UUID, name="input") -> db.PortDefinition:
    port_def = db.PortDefinition(
        id=uuid.uuid4(),
        component_version_id=component_version_id,
        name=name,
        port_type=db.PortType.INPUT,
        drives_output_schema=False,
    )
    session.add(port_def)
    session.commit()
    return port_def


def _make_graph_runner(session) -> db.GraphRunner:
    gr = db.GraphRunner(id=uuid.uuid4(), tag_version=None)
    session.add(gr)
    session.commit()
    return gr


def _make_port_mapping_via_output_instance(
    session,
    graph_runner_id: uuid.UUID,
    source_instance_id: uuid.UUID,
    source_output_port_instance_id: uuid.UUID,
    target_instance_id: uuid.UUID,
    target_port_definition_id: uuid.UUID,
) -> db.PortMapping:
    pm = db.PortMapping(
        id=uuid.uuid4(),
        graph_runner_id=graph_runner_id,
        source_instance_id=source_instance_id,
        source_port_definition_id=None,
        source_output_port_instance_id=source_output_port_instance_id,
        target_instance_id=target_instance_id,
        target_port_definition_id=target_port_definition_id,
        dispatch_strategy="direct",
    )
    session.add(pm)
    session.commit()
    return pm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_output_port_instances_cascade_deleted_with_component_instance():
    """Deleting a ComponentInstance cascade-deletes all its OutputPortInstances."""
    with get_db_session() as session:
        source = _make_component_instance(session)

        output_port_instance_repository.create_output_port_instance(
            session=session, component_instance_id=source.id, name="name"
        )
        output_port_instance_repository.create_output_port_instance(
            session=session, component_instance_id=source.id, name="age"
        )

        ports_before = output_port_instance_repository.get_output_port_instances_for_component_instance(
            session=session, component_instance_id=source.id
        )
        assert len(ports_before) == 2

        session.delete(source)
        session.commit()

        ports_after = (
            session.query(db.OutputPortInstance).filter(db.PortInstance.component_instance_id == source.id).all()
        )
        assert len(ports_after) == 0


def test_delete_output_port_instances_does_not_affect_input_port_instances():
    """delete_output_port_instances_for_component_instance only removes OUTPUT ports."""
    with get_db_session() as session:
        source = _make_component_instance(session)

        output_port_instance_repository.create_output_port_instance(
            session=session, component_instance_id=source.id, name="name"
        )
        output_port_instance_repository.create_output_port_instance(
            session=session, component_instance_id=source.id, name="age"
        )

        input_port = db.InputPortInstance(component_instance_id=source.id, name="output_format")
        session.add(input_port)
        session.commit()

        deleted = output_port_instance_repository.delete_output_port_instances_for_component_instance(
            session=session, component_instance_id=source.id
        )
        assert deleted == 2

        remaining_outputs = output_port_instance_repository.get_output_port_instances_for_component_instance(
            session=session, component_instance_id=source.id
        )
        assert len(remaining_outputs) == 0

        remaining_input = (
            session.query(db.InputPortInstance).filter(db.PortInstance.component_instance_id == source.id).first()
        )
        assert remaining_input is not None
        assert remaining_input.name == "output_format"


def test_source_component_deletion_cascade_removes_port_mapping():
    """Deleting the source ComponentInstance cascade-deletes PortMappings via source_instance_id."""
    with get_db_session() as session:
        source = _make_component_instance(session)
        target = _make_component_instance(session)
        target_port_def = _make_input_port_definition(session, target.component_version_id)
        graph_runner = _make_graph_runner(session)

        output_port = output_port_instance_repository.create_output_port_instance(
            session=session, component_instance_id=source.id, name="name"
        )
        port_mapping = _make_port_mapping_via_output_instance(
            session=session,
            graph_runner_id=graph_runner.id,
            source_instance_id=source.id,
            source_output_port_instance_id=output_port.id,
            target_instance_id=target.id,
            target_port_definition_id=target_port_def.id,
        )

        session.delete(source)
        session.commit()

        remaining_pm = session.query(db.PortMapping).filter(db.PortMapping.id == port_mapping.id).first()
        assert remaining_pm is None


def test_output_port_instance_deletion_nullifies_port_mapping_source():
    """Deleting an OutputPortInstance individually sets source_output_port_instance_id to NULL.

    The PortMapping survives but is left dangling — neither source FK is set.
    """
    with get_db_session() as session:
        source = _make_component_instance(session)
        target = _make_component_instance(session)
        target_port_def = _make_input_port_definition(session, target.component_version_id)
        graph_runner = _make_graph_runner(session)

        output_port = output_port_instance_repository.create_output_port_instance(
            session=session, component_instance_id=source.id, name="name"
        )
        port_mapping = _make_port_mapping_via_output_instance(
            session=session,
            graph_runner_id=graph_runner.id,
            source_instance_id=source.id,
            source_output_port_instance_id=output_port.id,
            target_instance_id=target.id,
            target_port_definition_id=target_port_def.id,
        )

        session.delete(output_port)
        session.commit()

        session.expire(port_mapping)
        pm = session.query(db.PortMapping).filter(db.PortMapping.id == port_mapping.id).first()

        assert pm is not None, "PortMapping should survive the OutputPortInstance deletion"
        assert pm.source_output_port_instance_id is None
        assert pm.source_instance_id == source.id


def test_get_source_port_name_returns_none_for_dangling_mapping():
    """get_source_port_name returns None when source_output_port_instance_id is SET NULL.

    This is the case logged as a warning and skipped in get_graph_service
    and agent_runner_service.
    """
    with get_db_session() as session:
        source = _make_component_instance(session)
        target = _make_component_instance(session)
        target_port_def = _make_input_port_definition(session, target.component_version_id)
        graph_runner = _make_graph_runner(session)

        output_port = output_port_instance_repository.create_output_port_instance(
            session=session, component_instance_id=source.id, name="name"
        )
        port_mapping = _make_port_mapping_via_output_instance(
            session=session,
            graph_runner_id=graph_runner.id,
            source_instance_id=source.id,
            source_output_port_instance_id=output_port.id,
            target_instance_id=target.id,
            target_port_definition_id=target_port_def.id,
        )

        session.delete(output_port)
        session.commit()

        session.expire(port_mapping)
        pm = session.query(db.PortMapping).filter(db.PortMapping.id == port_mapping.id).first()

        assert get_source_port_name(pm) is None
