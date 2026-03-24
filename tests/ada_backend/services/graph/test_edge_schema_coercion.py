from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from ada_backend.schemas.pipeline.graph_schema import EdgeSchema


def test_edge_schema_plain_uuid():
    edge = EdgeSchema(id=uuid4(), origin=uuid4(), destination=uuid4(), order=0)
    assert isinstance(edge.origin, UUID)
    assert isinstance(edge.destination, UUID)


def test_edge_schema_string_uuid():
    origin_id = str(uuid4())
    dest_id = str(uuid4())
    edge = EdgeSchema(id=uuid4(), origin=origin_id, destination=dest_id, order=0)
    assert edge.origin == UUID(origin_id)
    assert edge.destination == UUID(dest_id)


def test_edge_schema_dict_with_instance_id():
    """Regression: agents may pass {"instance_id": "uuid", "port_name": "output"} for origin."""
    origin_uuid = uuid4()
    dest_uuid = uuid4()
    edge = EdgeSchema(
        id=uuid4(),
        origin={"instance_id": str(origin_uuid), "port_name": "output"},
        destination={"instance_id": str(dest_uuid), "port_name": "messages"},
        order=0,
    )
    assert edge.origin == origin_uuid
    assert edge.destination == dest_uuid


def test_edge_schema_dict_with_id_key():
    origin_uuid = uuid4()
    edge = EdgeSchema(
        id=uuid4(),
        origin={"id": str(origin_uuid)},
        destination=uuid4(),
        order=0,
    )
    assert edge.origin == origin_uuid


def test_edge_schema_dict_missing_keys_raises():
    with pytest.raises(ValidationError):
        EdgeSchema(
            id=uuid4(),
            origin={"port_name": "output"},
            destination=uuid4(),
            order=0,
        )
