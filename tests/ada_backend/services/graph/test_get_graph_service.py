import uuid
import pytest

from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.schemas.pipeline.graph_schema import GraphGetResponse, EdgeSchema


class DummyComponentNode:
    def __init__(self, id, is_start_node=False):
        self.id = id
        self.is_start_node = is_start_node


class DummyEdge:
    def __init__(self, id, source_node_id, target_node_id, order=0):
        self.id = id
        self.source_node_id = source_node_id
        self.target_node_id = target_node_id
        self.order = order


class DummyEnvRel:
    def __init__(self, project_id):
        self.project_id = project_id


class DummyComponentInstance:
    def __init__(self, id):
        self.id = id
        self.definition = None


def test_get_graph_service_graph_not_found(monkeypatch):
    session = object()
    project_id = uuid.uuid4()
    graph_runner_id = uuid.uuid4()

    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.graph_runner_exists",
        lambda s, gid: False,
    )

    with pytest.raises(ValueError) as exc:
        get_graph_service(session, project_id, graph_runner_id)
    assert "not found" in str(exc.value)


def test_get_graph_service_env_not_bound(monkeypatch):
    session = object()
    project_id = uuid.uuid4()
    graph_runner_id = uuid.uuid4()

    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.graph_runner_exists",
        lambda s, gid: True,
    )
    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.get_env_relationship_by_graph_runner_id",
        lambda s, gid: None,
    )

    with pytest.raises(ValueError) as exc:
        get_graph_service(session, project_id, graph_runner_id)
    assert "not bound to any project" in str(exc.value)


def test_get_graph_service_env_mismatch(monkeypatch):
    session = object()
    project_id = uuid.uuid4()
    graph_runner_id = uuid.uuid4()

    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.graph_runner_exists",
        lambda s, gid: True,
    )
    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.get_env_relationship_by_graph_runner_id",
        lambda s, gid: DummyEnvRel(project_id=uuid.uuid4()),
    )

    with pytest.raises(ValueError) as exc:
        get_graph_service(session, project_id, graph_runner_id)
    assert "bound to project" in str(exc.value)


def test_get_graph_service_success(monkeypatch):
    session = object()
    project_id = uuid.uuid4()
    graph_runner_id = uuid.uuid4()

    # stub existence
    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.graph_runner_exists",
        lambda s, gid: True,
    )

    # env relationship points to our project
    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.get_env_relationship_by_graph_runner_id",
        lambda s, gid: DummyEnvRel(project_id=project_id),
    )

    # two component nodes
    n1 = DummyComponentNode(uuid.uuid4(), is_start_node=True)
    n2 = DummyComponentNode(uuid.uuid4(), is_start_node=False)
    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.get_component_nodes",
        lambda s, gid: [n1, n2],
    )

    # get_component_instance should return a simple object; patch the imported function path
    def fake_get_component_instance(s, ci_id, is_start_node=False):
        return DummyComponentInstance(ci_id)

    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.get_component_instance",
        fake_get_component_instance,
    )

    # no relationships for simplicity
    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.get_relationships",
        lambda s, node_id: [],
    )

    # edges
    e1 = DummyEdge(uuid.uuid4(), n1.id, n2.id, order=1)
    monkeypatch.setattr(
        "ada_backend.services.graph.get_graph_service.get_edges",
        lambda s, gid: [e1],
    )

    res = get_graph_service(session, project_id, graph_runner_id)
    assert isinstance(res, GraphGetResponse)
    assert len(res.component_instances) == 2
    assert len(res.edges) == 1
    assert isinstance(res.edges[0], EdgeSchema)
