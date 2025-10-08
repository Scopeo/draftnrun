import asyncio
import uuid

from ada_backend.database.models import ParameterType
from ada_backend.services import agents_service
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.parameter_schema import PipelineParameterReadSchema, PipelineParameterSchema
from ada_backend.schemas.agent_schema import AgentUpdateSchema
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateResponse


class DummyAgent:
    def __init__(self, id, name, description=None):
        self.id = id
        self.name = name
        self.description = description


class DummyProject:
    def __init__(self, id, name, organization_id):
        self.id = id
        self.name = name
        self.organization_id = organization_id
        self.created_at = "2025-01-01T00:00:00"
        self.updated_at = "2025-01-01T00:00:00"
        self.description = None


class DummyGraphResponse:
    def __init__(self, component_instances):
        self.component_instances = component_instances


class DummyComponentInstance:
    def __init__(self, id, component_id, parameters=None, is_start_node=False):
        self.id = id
        self.component_id = component_id
        self.parameters = parameters or []
        self.is_start_node = is_start_node


def test_build_ai_agent_component_appends_system_prompt():
    ai_id = uuid.uuid4()
    param = []
    system_prompt = "Hello system"
    comp = agents_service.build_ai_agent_component(
        ai_agent_instance_id=ai_id, model_parameters=param, system_prompt=system_prompt
    )
    assert isinstance(comp, ComponentInstanceSchema)
    # last parameter should be the system prompt
    assert comp.parameters[-1].name == agents_service.SYSTEM_PROMPT_PARAMETER_NAME
    assert comp.parameters[-1].value == system_prompt


def test_get_all_agents_service(monkeypatch):
    session = object()
    org_id = uuid.uuid4()

    dummy_agents = [DummyAgent(uuid.uuid4(), "A1", "desc1"), DummyAgent(uuid.uuid4(), "A2", None)]

    class DummyBinding:
        def __init__(self, graph_runner_id, environment):
            self.graph_runner_id = graph_runner_id
            self.environment = environment

    def fake_fetch_agents_with_graph_runners_by_organization(session_arg, organization_id_arg):
        assert session_arg is session
        assert organization_id_arg == org_id
        # return pairs (agent, binding) as the real repository does
        return [
            (dummy_agents[0], DummyBinding(uuid.uuid4(), "draft")),
            (dummy_agents[1], DummyBinding(uuid.uuid4(), "draft")),
        ]

    monkeypatch.setattr(
        agents_service,
        "fetch_agents_with_graph_runners_by_organization",
        fake_fetch_agents_with_graph_runners_by_organization,
    )

    result = agents_service.get_all_agents_service(session, org_id)
    assert len(result) == 2
    assert result[0].name == "A1"
    assert result[1].id == dummy_agents[1].id


def test_get_agent_by_id_service_project_not_found(monkeypatch):
    session = object()
    agent_id = uuid.uuid4()
    graph_runner_id = uuid.uuid4()

    def fake_get_project(session_arg, project_id):
        return None

    monkeypatch.setattr(agents_service, "get_project", fake_get_project)

    res = agents_service.get_agent_by_id_service(session, agent_id, graph_runner_id)
    # Should return ProjectNotFound exception instance
    assert isinstance(res, agents_service.ProjectNotFound)


def test_get_agent_by_id_service_with_components(monkeypatch):
    session = object()
    agent_id = uuid.uuid4()
    graph_runner_id = uuid.uuid4()

    proj = DummyProject(agent_id, "AgentName", uuid.uuid4())

    def fake_get_project(session_arg, project_id):
        return proj

    # Create a component instance that matches base_ai_agent
    base_ai_component_id = agents_service.COMPONENT_UUIDS["base_ai_agent"]
    # parameter with SYSTEM_PROMPT_PARAMETER_DEF_ID
    pp = PipelineParameterReadSchema(
        id=agents_service.SYSTEM_PROMPT_PARAMETER_DEF_ID,
        name="initial_prompt",
        value="foo",
        type=ParameterType.STRING,
        nullable=False,
        is_advanced=False,
    )
    comp_instance = DummyComponentInstance(uuid.uuid4(), base_ai_component_id, parameters=[pp], is_start_node=True)

    def fake_get_graph_service(session_arg, project_id, graph_runner_id):
        assert project_id == agent_id
        assert graph_runner_id == graph_runner_id
        return DummyGraphResponse(component_instances=[comp_instance])

    monkeypatch.setattr(agents_service, "get_project", fake_get_project)
    monkeypatch.setattr(agents_service, "get_graph_service", fake_get_graph_service)

    res = agents_service.get_agent_by_id_service(session, agent_id, graph_runner_id)
    assert res.name == proj.name
    assert res.system_prompt == "foo"
    assert isinstance(res.model_parameters, list)
    assert res.tools == []


def test_update_agent_service_builds_graph_and_calls_update(monkeypatch):
    session = object()
    user_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    graph_runner_id = uuid.uuid4()

    # prepare agent_data with one tool and one model parameter
    tool_id = uuid.uuid4()
    tool_instance = ComponentInstanceSchema(id=tool_id, component_id=uuid.uuid4(), parameters=[])
    model_param = PipelineParameterSchema(name="model_param", value="v1")
    agent_data = AgentUpdateSchema(
        name="A",
        organization_id=uuid.uuid4(),
        system_prompt="the-prompt",
        model_parameters=[model_param],
        tools=[tool_instance],
    )

    called = {}

    async def fake_update_graph_service(*args, **kwargs):
        # capture values for assertions (support kwargs and positional args)
        if kwargs:
            called["session"] = kwargs.get("session")
            called["graph_runner_id"] = kwargs.get("graph_runner_id")
            called["project_id"] = kwargs.get("project_id")
            called["graph_project"] = kwargs.get("graph_project")
            called["user_id"] = kwargs.get("user_id")
        else:
            # fallback to positional mapping
            called["session"] = args[0] if len(args) > 0 else None
            called["graph_runner_id"] = args[1] if len(args) > 1 else None
            called["project_id"] = args[2] if len(args) > 2 else None
            called["graph_project"] = args[3] if len(args) > 3 else None
            called["user_id"] = args[4] if len(args) > 4 else None
        return GraphUpdateResponse(graph_id=called["graph_runner_id"])

    monkeypatch.setattr(agents_service, "update_graph_service", fake_update_graph_service)

    res = asyncio.run(agents_service.update_agent_service(session, user_id, agent_id, graph_runner_id, agent_data))

    # verify update_graph_service was called with expected values
    assert called["session"] is session
    assert called["graph_runner_id"] == graph_runner_id
    assert called["project_id"] == agent_id
    assert called["user_id"] == user_id

    graph_project = called["graph_project"]
    # relationships should include one entry linking version_id to the tool
    assert len(graph_project.relationships) == 1
    rel = graph_project.relationships[0]
    assert rel.parent_component_instance_id == graph_runner_id
    assert rel.child_component_instance_id == tool_id

    # component_instances should contain the provided tool and the built AI agent
    assert any(ci.id == tool_id for ci in graph_project.component_instances)
    # AI agent instance should have id equal to version_id and contain system prompt param
    ai_instances = [ci for ci in graph_project.component_instances if ci.id == graph_runner_id]
    assert len(ai_instances) == 1
    ai = ai_instances[0]
    assert any(
        p.name == agents_service.SYSTEM_PROMPT_PARAMETER_NAME and p.value == "the-prompt" for p in ai.parameters
    )
    # response should be GraphUpdateResponse with graph_id == version_id
    assert isinstance(res, GraphUpdateResponse)
    assert res.graph_id == graph_runner_id
