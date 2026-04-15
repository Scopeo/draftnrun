import logging
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import ada_backend.services.agent_builder_service as agent_builder_service
import ada_backend.services.entity_factory as entity_factory
from ada_backend.utils.secret_resolver import replace_secret_placeholders
from engine.components.utils_prompt import fill_prompt_template
from engine.field_expressions.ast import ConcatNode, LiteralNode, VarNode
from engine.graph_runner.field_expression_management import evaluate_expression
from engine.secret import SecretValue, unwrap_secrets
from engine.trace.serializer import serialize_to_json

LEAK_MARKER = "SUPER_SECRET_API_KEY_12345"


def test_secret_value_fstring_masks_plaintext():
    secret = SecretValue(LEAK_MARKER)
    assert f"{secret}" == "***"
    assert LEAK_MARKER not in f"{secret}"


def test_unwrap_secrets_preserves_dict_keys_and_unwraps_values():
    key_secret = SecretValue("dict-key-secret")
    payload = {"param_name": SecretValue(LEAK_MARKER), key_secret: "value"}

    result = unwrap_secrets(payload)

    assert result["param_name"] == LEAK_MARKER
    assert key_secret in result
    assert "dict-key-secret" not in result
    assert result[key_secret] == "value"


def test_replace_secret_placeholders_does_not_log_plaintext(caplog):
    payload = {"headers": {"Authorization": "Bearer @{ENV:MY_KEY}"}}

    with caplog.at_level(logging.DEBUG):
        result = replace_secret_placeholders(payload, {"MY_KEY": SecretValue(LEAK_MARKER)})

    assert result["headers"]["Authorization"] == f"Bearer {LEAK_MARKER}"
    assert LEAK_MARKER not in caplog.text


def test_fill_prompt_template_unwraps_for_execution_without_log_leak(caplog):
    with caplog.at_level(logging.DEBUG):
        result = fill_prompt_template(
            "Bearer {{api_key}}",
            component_name="qa_component",
            variables={"api_key": SecretValue(LEAK_MARKER)},
        )

    assert result == f"Bearer {LEAK_MARKER}"
    assert LEAK_MARKER not in caplog.text


def test_serialize_to_json_masks_secret_values_in_nested_payload():
    payload = {
        "token": SecretValue(LEAK_MARKER),
        "nested": [{"api_key": SecretValue("another-secret")}],
        "public": "ok",
    }

    serialized = serialize_to_json(payload)

    assert LEAK_MARKER not in serialized
    assert "another-secret" not in serialized
    assert '"***"' in serialized
    assert "ok" in serialized


@pytest.mark.asyncio
async def test_resolve_oauth_access_token_unwraps_secret_value_before_uuid(monkeypatch, caplog):
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
    monkeypatch.setattr(entity_factory, "get_run_variables", lambda: {"oauth_connection": SecretValue(connection_id)})
    monkeypatch.setattr(entity_factory, "get_oauth_access_token", fake_get_oauth_access_token)

    with caplog.at_level(logging.INFO):
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
        lambda session, pid: [SimpleNamespace(key="API_KEY", secret=SecretValue(LEAK_MARKER))],
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
            variables={"api_key": SecretValue(LEAK_MARKER)},
        )

    assert isinstance(result, SecretValue)
    assert LEAK_MARKER not in caplog.text
    assert "***" in caplog.text


def test_evaluate_expression_concatnode_unwraps_for_runtime_without_log_leak(caplog):
    expression = ConcatNode(parts=[LiteralNode(value="Bearer "), VarNode(name="api_key")])

    with caplog.at_level(logging.DEBUG):
        result = evaluate_expression(
            expression=expression,
            target_field_name="auth_header",
            tasks={},
            variables={"api_key": SecretValue(LEAK_MARKER)},
        )

    assert result == f"Bearer {LEAK_MARKER}"
    assert LEAK_MARKER not in caplog.text
