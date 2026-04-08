"""Tests for OutputPortInstance lifecycle and cascade behaviors.

Verifies what happens at the DB level when a component instance with dynamic
output ports is involved:

- Deleting a ComponentInstance cascade-deletes its OutputPortInstances.
- delete_output_port_instances_for_component_instance only touches OUTPUT ports,
  leaving INPUT port instances on the same component untouched.
"""

import uuid

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories import output_port_instance_repository

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
