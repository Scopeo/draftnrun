import pytest

from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.services.entity_factory import OAuthBinding, OAuthComponentFactory
from ada_backend.services.registry import FACTORY_REGISTRY
from engine.components.synthesizer import Synthesizer
from engine.components.tools.google_calendar_mcp_tool import GoogleCalendarMCPTool
from engine.components.tools.mcp.remote_mcp_tool import RemoteMCPTool
from engine.components.types import ComponentAttributes, ToolDescription
from engine.integrations.gmail.gmail_sender_v2 import GmailSenderV2
from engine.integrations.mail_sender import MailSender
from engine.integrations.providers import OAuthProvider
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_context import set_trace_manager
from tests.mocks.trace_manager import MockTraceManager


@pytest.mark.asyncio
async def test_synthesizer_registration():
    set_trace_manager(MockTraceManager(project_name="test_project"))
    factory = FACTORY_REGISTRY.get(component_version_id=COMPONENT_VERSION_UUIDS["synthesizer"])
    assert factory is not None

    synthesizer = await factory(
        trace_manager=MockTraceManager(project_name="test_project"),
        completion_model="openai:gpt-4.1-mini",
        temperature=0.99,
    )
    assert synthesizer is not None
    assert isinstance(synthesizer, Synthesizer)
    assert synthesizer._completion_service is not None
    assert isinstance(synthesizer._completion_service, CompletionService)
    assert synthesizer._completion_service._model_name == "gpt-4.1-mini"
    assert synthesizer._completion_service._invocation_parameters.get("temperature") == 0.99


@pytest.mark.asyncio
async def test_remote_mcp_factory_calls_async_constructor(monkeypatch):
    set_trace_manager(MockTraceManager(project_name="test_project"))

    async def fake_from_mcp_server(cls, **kwargs):
        return {"constructed_with": kwargs}

    monkeypatch.setattr(RemoteMCPTool, "from_mcp_server", classmethod(fake_from_mcp_server))

    tool_desc = ToolDescription(
        name="placeholder",
        description="placeholder",
        tool_properties={},
        required_tool_properties=[],
    )

    result = await FACTORY_REGISTRY.create(
        component_version_id=COMPONENT_VERSION_UUIDS["remote_mcp_tool"],
        component_attributes=ComponentAttributes(component_instance_name="remote"),
        server_url="https://mcp.example.com/sse",
        tool_description=tool_desc,
    )

    assert result["constructed_with"]["server_url"] == "https://mcp.example.com/sse"
    assert "tool_description" not in result["constructed_with"]


def test_google_calendar_mcp_tool_registered():
    """Verify the Google Calendar MCP component is registered with the correct factory."""
    factory = FACTORY_REGISTRY.get(component_version_id=COMPONENT_VERSION_UUIDS["google_calendar_mcp_tool"])
    assert factory is not None
    assert isinstance(factory, OAuthComponentFactory)
    assert factory.entity_class is GoogleCalendarMCPTool
    assert factory.oauth_bindings == [
        OAuthBinding(
            param_name="oauth_connection_id",
            provider_config_key=OAuthProvider.GOOGLE_CALENDAR,
            target_param_name="access_token",
        ),
    ]
    assert factory.constructor_method == "from_access_token"


def test_google_calendar_neverdrop_mcp_tool_registered():
    factory = FACTORY_REGISTRY.get(
        component_version_id=COMPONENT_VERSION_UUIDS["google_calendar_neverdrop_mcp_tool"]
    )
    assert factory is not None
    assert isinstance(factory, OAuthComponentFactory)
    assert factory.entity_class is GoogleCalendarMCPTool
    assert factory.oauth_bindings == [
        OAuthBinding(
            param_name="oauth_connection_id",
            provider_config_key=OAuthProvider.GOOGLE_CALENDAR_NEVERDROP,
            target_param_name="access_token",
        ),
    ]
    assert factory.constructor_method == "from_access_token"


def test_gmail_neverdrop_sender_registered():
    factory = FACTORY_REGISTRY.get(component_version_id=COMPONENT_VERSION_UUIDS["gmail_neverdrop_sender"])
    assert factory is not None
    assert isinstance(factory, OAuthComponentFactory)
    assert factory.entity_class is GmailSenderV2
    assert factory.oauth_bindings == [
        OAuthBinding(
            param_name="oauth_connection_id",
            provider_config_key=OAuthProvider.GMAIL_NEVERDROP,
            target_param_name="access_token",
        ),
    ]


def test_mail_sender_registered():
    factory = FACTORY_REGISTRY.get(component_version_id=COMPONENT_VERSION_UUIDS["mail_sender"])
    assert factory is not None
    assert isinstance(factory, OAuthComponentFactory)
    assert factory.entity_class is MailSender
    assert factory.oauth_bindings == [
        OAuthBinding(
            param_name="gmail_oauth_connection_id",
            provider_config_key=OAuthProvider.GMAIL,
            target_param_name="gmail_access_token",
        ),
        OAuthBinding(
            param_name="outlook_oauth_connection_id",
            provider_config_key=OAuthProvider.OUTLOOK,
            target_param_name="outlook_access_token",
        ),
    ]


@pytest.mark.asyncio
async def test_mail_sender_factory_resolves_oauth_bindings(monkeypatch):
    set_trace_manager(MockTraceManager(project_name="test_project"))

    resolved_requests: list[tuple[str | None, str]] = []

    async def fake_resolve_oauth_access_token(definition_id: str | None, provider_config_key: str) -> str | None:
        resolved_requests.append((definition_id, provider_config_key))
        tokens = {
            OAuthProvider.GMAIL: "gmail-access-token",
            OAuthProvider.OUTLOOK: "outlook-access-token",
        }
        return tokens[provider_config_key]

    monkeypatch.setattr(
        "ada_backend.services.entity_factory.resolve_oauth_access_token",
        fake_resolve_oauth_access_token,
    )

    component = await FACTORY_REGISTRY.create(
        component_version_id=COMPONENT_VERSION_UUIDS["mail_sender"],
        component_attributes=ComponentAttributes(component_instance_name="mail_sender"),
        gmail_oauth_connection_id="gmail-definition-id",
        outlook_oauth_connection_id="outlook-definition-id",
    )

    assert isinstance(component, MailSender)
    assert resolved_requests == [
        ("gmail-definition-id", OAuthProvider.GMAIL),
        ("outlook-definition-id", OAuthProvider.OUTLOOK),
    ]
    assert component._gmail_access_token.get_secret_value() == "gmail-access-token"
    assert component._outlook_access_token.get_secret_value() == "outlook-access-token"
