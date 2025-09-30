import uuid

import pytest
from fastapi import HTTPException

from ada_backend.services.graph.deploy_graph_service import deploy_graph_service
from ada_backend.database.models import EnvType


class DummyEnvRel:
    def __init__(self, environment=None):
        self.environment = environment


class DummyGraphRunner:
    def __init__(self, id):
        self.id = id


def test_deploy_graph_service_graph_not_found(monkeypatch):
    session = object()
    graph_runner_id = uuid.uuid4()
    project_id = uuid.uuid4()

    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.graph_runner_exists", lambda s, graph_id: False
    )

    with pytest.raises(HTTPException) as exc:
        deploy_graph_service(session, graph_runner_id, project_id)
    assert exc.value.status_code == 404


def test_deploy_graph_service_env_not_bound(monkeypatch):
    session = object()
    graph_runner_id = uuid.uuid4()
    project_id = uuid.uuid4()

    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.graph_runner_exists", lambda s, graph_id: True
    )
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.get_env_relationship_by_graph_runner_id",
        lambda session, graph_runner_id: None,
    )

    with pytest.raises(HTTPException) as exc:
        deploy_graph_service(session, graph_runner_id, project_id)
    assert exc.value.status_code == 404


def test_deploy_graph_service_already_production(monkeypatch):
    session = object()
    graph_runner_id = uuid.uuid4()
    project_id = uuid.uuid4()

    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.graph_runner_exists", lambda s, graph_id: True
    )
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.get_env_relationship_by_graph_runner_id",
        lambda session, graph_runner_id: DummyEnvRel(environment=EnvType.PRODUCTION),
    )

    with pytest.raises(HTTPException) as exc:
        deploy_graph_service(session, graph_runner_id, project_id)
    assert exc.value.status_code == 400


def test_deploy_graph_service_success_no_previous(monkeypatch):
    session = object()
    graph_runner_id = uuid.uuid4()
    project_id = uuid.uuid4()

    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.graph_runner_exists", lambda s, graph_id: True
    )
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.get_env_relationship_by_graph_runner_id",
        lambda session, graph_runner_id: DummyEnvRel(environment=EnvType.DRAFT),
    )
    # no previous production graph
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.get_graph_runner_for_env",
        lambda session, project_id, env: None,
    )

    # clone returns a new id
    new_id = uuid.uuid4()
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.clone_graph_runner",
        lambda session, graph_runner_id_to_copy, project_id: new_id,
    )

    # bind and update just need to be present; patch to no-op
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.bind_graph_runner_to_project", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.update_graph_runner_env", lambda *a, **k: None
    )

    res = deploy_graph_service(session, graph_runner_id, project_id)
    assert res.project_id == project_id
    assert res.draft_graph_runner_id == new_id
    assert res.prod_graph_runner_id == graph_runner_id
    assert res.previous_prod_graph_runner_id is None


def test_deploy_graph_service_success_with_previous(monkeypatch):
    session = object()
    graph_runner_id = uuid.uuid4()
    project_id = uuid.uuid4()

    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.graph_runner_exists", lambda s, graph_id: True
    )
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.get_env_relationship_by_graph_runner_id",
        lambda session, graph_runner_id: DummyEnvRel(environment=EnvType.DRAFT),
    )

    previous = DummyGraphRunner(uuid.uuid4())
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.get_graph_runner_for_env",
        lambda session, project_id, env: previous,
    )

    new_id = uuid.uuid4()
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.clone_graph_runner",
        lambda session, graph_runner_id_to_copy, project_id: new_id,
    )
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.bind_graph_runner_to_project", lambda *a, **k: None
    )
    # make update_graph_runner_env a no-op
    monkeypatch.setattr(
        "ada_backend.services.graph.deploy_graph_service.update_graph_runner_env", lambda *a, **k: None
    )

    res = deploy_graph_service(session, graph_runner_id, project_id)
    assert res.project_id == project_id
    assert res.draft_graph_runner_id == new_id
    assert res.prod_graph_runner_id == graph_runner_id
    assert res.previous_prod_graph_runner_id == previous.id
