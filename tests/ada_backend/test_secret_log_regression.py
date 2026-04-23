import json
import logging
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import UUID, uuid4

import pandas as pd
import pytest
from pydantic import SecretStr

import ada_backend.services.agent_builder_service as agent_builder_service
import ada_backend.services.entity_factory as entity_factory
import ada_backend.services.trace_service as trace_service
import engine.graph_runner.graph_runner as graph_runner_module
from ada_backend.utils.secret_resolver import replace_secret_placeholders
from engine.components.utils_prompt import fill_prompt_template
from engine.field_expressions.ast import ConcatNode, LiteralNode, VarNode
from engine.graph_runner.field_expression_management import evaluate_expression
from engine.secret_utils import unwrap_secrets
from engine.trace.serializer import serialize_to_json
from shared.log_redaction import redact_sensitive

LEAK_MARKER = "SUPER_SECRET_API_KEY_12345"


def test_secret_str_fstring_masks_plaintext():
    secret = SecretStr(LEAK_MARKER)
    assert f"{secret}" == "**********"
    assert LEAK_MARKER not in f"{secret}"


def test_unwrap_secrets_preserves_dict_keys_and_unwraps_values():
    key_secret = SecretStr("dict-key-secret")
    payload = {"param_name": SecretStr(LEAK_MARKER), key_secret: "value"}

    result = unwrap_secrets(payload)

    assert result["param_name"] == LEAK_MARKER
    assert key_secret in result
    assert "dict-key-secret" not in result
    assert result[key_secret] == "value"


def test_replace_secret_placeholders_does_not_log_plaintext(caplog):
    payload = {"headers": {"Authorization": "Bearer @{ENV:MY_KEY}"}}

    with caplog.at_level(logging.DEBUG):
        result = replace_secret_placeholders(payload, {"MY_KEY": SecretStr(LEAK_MARKER)})

    assert result["headers"]["Authorization"] == f"Bearer {LEAK_MARKER}"
    assert LEAK_MARKER not in caplog.text


def test_fill_prompt_template_unwraps_for_execution_without_log_leak(caplog):
    with caplog.at_level(logging.DEBUG):
        result = fill_prompt_template(
            "Bearer {{api_key}}",
            component_name="qa_component",
            variables={"api_key": SecretStr(LEAK_MARKER)},
        )

    assert result == f"Bearer {LEAK_MARKER}"
    assert LEAK_MARKER not in caplog.text


def test_serialize_to_json_masks_secret_values_in_nested_payload():
    payload = {
        "token": SecretStr(LEAK_MARKER),
        "nested": [{"api_key": SecretStr("another-secret")}],
        "public": "ok",
    }

    serialized = serialize_to_json(payload)

    assert LEAK_MARKER not in serialized
    assert "another-secret" not in serialized
    assert '"[REDACTED]"' in serialized
    assert "ok" in serialized


@pytest.mark.asyncio
async def test_resolve_oauth_access_token_unwraps_secretstr_before_uuid(monkeypatch, caplog):
    definition_id = str(uuid4())
    connection_id = str(uuid4())
    captured: dict[str, UUID] = {}

    async def fake_get_oauth_access_token(*, session, oauth_connection_id, provider_config_key):
        captured["oauth_connection_id"] = oauth_connection_id
        captured["provider_config_key"] = provider_config_key
        return "access-token"

    monkeypatch.setattr(entity_factory, "get_db_session", lambda: nullcontext("session"))
    monkeypatch.setattr(
        entity_factory,
        "get_oauth_definition_by_id",
        lambda session, definition_uuid: SimpleNamespace(name="oauth_connection", default_value=None),
    )
    monkeypatch.setattr(entity_factory, "get_run_variables", lambda: {"oauth_connection": SecretStr(connection_id)})
    monkeypatch.setattr(entity_factory, "get_oauth_access_token", fake_get_oauth_access_token)

    with caplog.at_level(logging.DEBUG):
        token = await entity_factory.resolve_oauth_access_token(definition_id, "github")

    assert token == "access-token"
    assert captured["oauth_connection_id"] == UUID(connection_id)
    assert captured["provider_config_key"] == "github"
    assert connection_id not in caplog.text


@pytest.mark.asyncio
async def test_instantiate_component_error_logs_only_param_names_after_secret_resolution(monkeypatch, caplog):
    component_version_id = uuid4()
    component_instance_id = uuid4()
    project_id = uuid4()

    class FakeRegistry:
        @staticmethod
        def get(component_version_id):
            return SimpleNamespace(entity_class=None)

        @staticmethod
        async def create(component_version_id, **kwargs):
            raise RuntimeError("boom")

    component_instance = SimpleNamespace(
        id=component_instance_id,
        name="Test Component",
        ref="test_component_ref",
        component_version_id=component_version_id,
    )

    monkeypatch.setattr(
        agent_builder_service,
        "get_component_instance_by_id",
        lambda session, cid: component_instance,
    )
    monkeypatch.setattr(
        agent_builder_service,
        "get_component_name_from_instance",
        lambda session, cid: "Test Component",
    )
    monkeypatch.setattr(
        agent_builder_service,
        "get_component_params",
        lambda session, cid, project_id=None: {"auth_header": "Bearer @{ENV:API_KEY}", "model": "test-model"},
    )
    monkeypatch.setattr(agent_builder_service, "get_integration_from_component", lambda session, cvid: None)
    monkeypatch.setattr(agent_builder_service, "get_component_sub_components", lambda session, cid: [])
    monkeypatch.setattr(
        agent_builder_service,
        "get_global_parameters_by_component_version_id",
        lambda session, cvid: [],
    )
    monkeypatch.setattr(agent_builder_service, "get_base_component_from_version", lambda session, cvid: None)
    monkeypatch.setattr(agent_builder_service, "set_current_project_id", lambda pid: None)
    monkeypatch.setattr(
        agent_builder_service,
        "get_organization_secrets_from_project_id",
        lambda session, pid: [SimpleNamespace(key="API_KEY", secret=SecretStr(LEAK_MARKER))],
    )
    monkeypatch.setattr(agent_builder_service, "FACTORY_REGISTRY", FakeRegistry())

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ValueError, match="Failed to instantiate component 'Test Component'"):
            await agent_builder_service.instantiate_component(
                session=object(),
                component_instance_id=component_instance_id,
                project_id=project_id,
                variables=None,
            )

    assert LEAK_MARKER not in caplog.text
    assert "with input param names:" in caplog.text
    assert "Input parameter names:" in caplog.text
    assert "auth_header" in caplog.text
    assert "model" in caplog.text


def test_evaluate_expression_varnode_logs_masked_secret(caplog):
    expression = VarNode(name="api_key")

    with caplog.at_level(logging.DEBUG):
        result = evaluate_expression(
            expression=expression,
            target_field_name="auth_header",
            tasks={},
            variables={"api_key": SecretStr(LEAK_MARKER)},
        )

    assert isinstance(result, SecretStr)
    assert LEAK_MARKER not in caplog.text
    assert "type=SecretStr" in caplog.text


def test_evaluate_expression_concatnode_unwraps_for_runtime_without_log_leak(caplog):
    # TODO(DRA-1255): Invert this expectation in the follow-up. The composed
    # string should preserve secret taint long enough for child spans to stay
    # masked, rather than returning plaintext here.
    expression = ConcatNode(parts=[LiteralNode(value="Bearer "), VarNode(name="api_key")])

    with caplog.at_level(logging.DEBUG):
        result = evaluate_expression(
            expression=expression,
            target_field_name="auth_header",
            tasks={},
            variables={"api_key": SecretStr(LEAK_MARKER)},
        )

    assert result == f"Bearer {LEAK_MARKER}"
    assert LEAK_MARKER not in caplog.text


def test_graph_runner_set_from_expression_does_not_log_evaluated_value():
    with open(graph_runner_module.__file__, "r", encoding="utf-8") as handle:
        module_src = handle.read()
    assert "Set {node_id}.{field_name} from {log_prefix}: {evaluated_value}" not in module_src
    assert 'LOGGER.debug(f"Set {node_id}.{field_name} from {log_prefix}")' in module_src


@pytest.mark.asyncio
async def test_ai_agent_tool_call_log_format_is_keys_only(caplog):
    import engine.components.ai_agent as ai_agent_module

    class FakeTool:
        async def run(self, **kwargs):
            return ai_agent_module.AgentPayload(messages=[ai_agent_module.ChatMessage(role="assistant", content="ok")])

    agent = object.__new__(ai_agent_module.AIAgent)
    agent._tool_registry = {"search_docs": (FakeTool(), None, {})}

    tool_call = SimpleNamespace(
        id="call_123",
        function=SimpleNamespace(
            name="search_docs",
            arguments=json.dumps({"api_key": LEAK_MARKER, "query": "hello"}),
        ),
    )

    with caplog.at_level(logging.DEBUG, logger=ai_agent_module.LOGGER.name):
        tool_call_id, tool_output = await agent._run_tool_call(tool_call=tool_call, ctx={"request_id": "req_1"})

    ai_agent_messages = [
        record.getMessage() for record in caplog.records if record.name == ai_agent_module.LOGGER.name
    ]
    combined_logs = "\n".join(ai_agent_messages)

    assert tool_call_id == "call_123"
    assert tool_output.messages[0].content == "ok"
    assert LEAK_MARKER not in combined_logs
    assert "argument keys" in combined_logs
    assert "api_key" in combined_logs
    assert "query" in combined_logs
    assert '"api_key":' not in combined_logs


def test_trace_service_error_log_does_not_include_input_data(caplog, monkeypatch):
    monkeypatch.setattr(
        trace_service,
        "_safe_json_loads",
        lambda raw: [{"messages": None, "secret": LEAK_MARKER}] if raw == "input" else [],
    )

    row = pd.Series({
        "input_content": "input",
        "output_content": "[]",
        "attributes": {"llm": {}},
        "events": "[]",
    })

    with caplog.at_level(logging.ERROR):
        try:
            trace_service.get_attributes_with_messages("LLM", row, filter_to_last_message=True)
        except Exception:
            pass

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected error log on unparseable messages"
    for record in error_records:
        assert LEAK_MARKER not in record.getMessage()


def test_redis_client_payload_log_is_keys_only(monkeypatch, caplog):
    import ada_backend.utils.redis_client as redis_client_module

    class FakeRedisClient:
        def xadd(self, stream_name, payload):
            return "1-0"

    class FakeSourceAttributes:
        def model_dump(self):
            return {"api_key": LEAK_MARKER, "public": "ok"}

    monkeypatch.setattr(redis_client_module, "get_redis_client", lambda: FakeRedisClient())
    monkeypatch.setattr(redis_client_module.LOGGER, "propagate", True)

    with caplog.at_level(logging.DEBUG, logger=redis_client_module.LOGGER.name):
        assert redis_client_module.push_ingestion_task(
            ingestion_id="ing_1",
            source_name="Secret Source",
            source_type="api",
            organization_id="org_1",
            task_id="task_1",
            source_attributes=FakeSourceAttributes(),
            source_id="source_1",
        )
        assert redis_client_module.push_webhook_event(
            webhook_id=uuid4(),
            provider="github",
            payload={"authorization": f"Bearer {LEAK_MARKER}", "public": "ok"},
            event_id="evt_1",
        )

    redis_client_messages = [
        record.getMessage() for record in caplog.records if record.name == redis_client_module.LOGGER.name
    ]
    combined_logs = "\n".join(redis_client_messages)

    assert LEAK_MARKER not in combined_logs
    assert "Prepared ingestion payload for Redis stream" in combined_logs
    assert "source_id=source_1" in combined_logs
    assert "keys=['ingestion_id'" in combined_logs
    assert "Prepared webhook payload for Redis stream" in combined_logs
    assert "payload_keys=['authorization', 'public']" in combined_logs
    assert f"Bearer {LEAK_MARKER}" not in combined_logs


def test_mcp_tool_parameters_span_attribute_masks_secretstr_and_sensitive_keys():
    arguments = {
        "api_key": SecretStr(LEAK_MARKER),
        "authorization": LEAK_MARKER,
        "prompt": "hi",
    }

    tool_parameters_attr = serialize_to_json(redact_sensitive(arguments))

    assert LEAK_MARKER not in tool_parameters_attr
    assert "[REDACTED]" in tool_parameters_attr
    assert "hi" in tool_parameters_attr


def test_ai_agent_llm_input_messages_serialize_masks_secretstr():
    messages = [
        {"role": "system", "content": "safe"},
        {"role": "user", "content": SecretStr(LEAK_MARKER)},
    ]

    serialized = serialize_to_json(messages)

    assert LEAK_MARKER not in serialized
    assert "safe" in serialized


# A10
def test_serialize_to_json_masks_secretstr_inside_pydantic_model():
    from pydantic import BaseModel

    class MyModel(BaseModel):
        api_key: SecretStr
        public: str

    payload = MyModel(api_key=SecretStr(LEAK_MARKER), public="visible")

    serialized = serialize_to_json(payload)

    assert LEAK_MARKER not in serialized
    assert "visible" in serialized
    assert "[REDACTED]" in serialized


# A11
def test_unwrap_secret_and_unwrap_secrets_do_not_log_plaintext(caplog):
    with caplog.at_level(logging.DEBUG):
        plain = unwrap_secrets({"key": SecretStr(LEAK_MARKER), "nested": [SecretStr(LEAK_MARKER)]})

    assert plain["key"] == LEAK_MARKER
    assert plain["nested"] == [LEAK_MARKER]
    assert LEAK_MARKER not in caplog.text


# A20
def test_ai_agent_uses_reveal_secrets_false_for_span_and_true_for_llm():
    import engine.components.ai_agent as ai_agent_module

    with open(ai_agent_module.__file__, "r", encoding="utf-8") as fh:
        src = fh.read()

    assert "reveal_secrets=False" in src, "ai_agent must use reveal_secrets=False for span"
    assert "LLM_INPUT_MESSAGES" in src, "ai_agent must set LLM_INPUT_MESSAGES span attribute"
    masked_idx = src.index("reveal_secrets=False")
    assert "fill_prompt_template" in src[:masked_idx], "fill_prompt_template must be called before masked variant"


# A21
def test_llm_call_uses_reveal_secrets_false_for_span_and_true_for_llm():
    import engine.components.llm_call as llm_call_module

    with open(llm_call_module.__file__, "r", encoding="utf-8") as fh:
        src = fh.read()

    assert "reveal_secrets=False" in src, "llm_call must use reveal_secrets=False for span"
    fill_idx = src.index("fill_prompt_template")
    masked_idx = src.index("reveal_secrets=False")
    assert fill_idx < masked_idx, "fill_prompt_template (reveal) must appear before reveal_secrets=False variant"
