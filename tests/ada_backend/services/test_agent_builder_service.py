import uuid
from uuid import UUID

import pytest

from ada_backend.services import agent_builder_service as absrv


class DummyParam:
    def __init__(self, name, value=None, order=None, organization_secret_id=None, organization_secret=None):
        self.parameter_definition = type("PD", (), {"name": name})
        self._value = value
        self.order = order
        self.organization_secret_id = organization_secret_id
        self.organization_secret = organization_secret

    def get_value(self):
        return self._value


class DummyOrgSecret:
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret


def test_get_component_params_singleton(monkeypatch):
    session = object()
    comp_id = uuid.uuid4()

    # One basic parameter without order
    p = DummyParam("param1", value="v")

    monkeypatch.setattr(absrv, "get_component_basic_parameters", lambda s, cid: [p])

    res = absrv.get_component_params(session, comp_id)
    assert res["param1"] == "v"


def test_get_component_params_ordered(monkeypatch):
    session = object()
    comp_id = uuid.uuid4()

    p1 = DummyParam("listparam", value="a", order=2)
    p2 = DummyParam("listparam", value="b", order=1)

    monkeypatch.setattr(absrv, "get_component_basic_parameters", lambda s, cid: [p1, p2])

    res = absrv.get_component_params(session, comp_id)
    assert res["listparam"] == ["b", "a"]


def test_get_component_params_org_secret_missing(monkeypatch):
    session = object()
    comp_id = uuid.uuid4()

    # Parameter referencing organization secret but none available
    secret = type("S", (), {"key": "k"})
    p = DummyParam("param_secret", value=None, organization_secret_id=uuid.uuid4(), organization_secret=secret)

    monkeypatch.setattr(absrv, "get_component_basic_parameters", lambda s, cid: [p])
    monkeypatch.setattr(absrv, "get_organization_secrets_from_project_id", lambda s, project_id, key: [])

    with pytest.raises(ValueError):
        absrv.get_component_params(session, comp_id, project_id=uuid.uuid4())


def test__get_tool_description_not_found(monkeypatch):
    session = object()
    comp_inst = type("CI", (), {"id": uuid.uuid4(), "component_id": uuid.uuid4()})

    monkeypatch.setattr(absrv, "get_tool_description", lambda s, cid: None)
    monkeypatch.setattr(absrv, "get_tool_description_component", lambda s, cid: None)

    res = absrv._get_tool_description(session, comp_inst)
    assert res is None


class DummyDBTool:
    def __init__(self):
        self.name = "My Tool"
        self.description = "desc"
        self.tool_properties = {"p": {"type": "string"}}
        self.required_tool_properties = []


def test__get_tool_description_found(monkeypatch):
    session = object()
    ci_id = uuid.uuid4()
    cid = uuid.uuid4()
    comp_inst = type("CI", (), {"id": ci_id, "component_id": cid})

    monkeypatch.setattr(absrv, "get_tool_description", lambda s, id: DummyDBTool())
    monkeypatch.setattr(absrv, "get_tool_description_component", lambda s, id: None)

    td = absrv._get_tool_description(session, comp_inst)
    assert td.name == "My_Tool"


def test_instantiate_component_not_found(monkeypatch):
    session = object()
    comp_id = uuid.uuid4()

    monkeypatch.setattr(absrv, "get_component_instance_by_id", lambda s, id: None)

    with pytest.raises(ValueError):
        absrv.instantiate_component(session, comp_id)
