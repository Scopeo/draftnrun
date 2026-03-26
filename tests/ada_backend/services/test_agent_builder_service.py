"""Tests for _should_skip_oauth_tool in agent_builder_service."""

import uuid
from unittest.mock import MagicMock, patch

from ada_backend.services.agent_builder_service import _should_skip_oauth_tool
from ada_backend.services.entity_factory import OAuthComponentFactory


def _real_oauth_factory():
    class _Dummy:
        def __init__(self, access_token=None):
            pass

    return OAuthComponentFactory(entity_class=_Dummy, provider_config_key="test")


def _child_instance(component_version_id=None):
    ci = MagicMock()
    ci.id = uuid.uuid4()
    ci.component_version_id = component_version_id or uuid.uuid4()
    return ci


def test_skips_oauth_tool_with_no_connection(monkeypatch):
    session = MagicMock()
    child = _child_instance()
    oauth_factory = _real_oauth_factory()

    with patch("ada_backend.services.agent_builder_service.FACTORY_REGISTRY") as mock_registry, \
         patch("ada_backend.services.agent_builder_service.has_oauth_connection", return_value=False):
        mock_registry.get.return_value = oauth_factory
        assert _should_skip_oauth_tool(session, child, skip_flag=True) is True


def test_does_not_skip_oauth_tool_when_flag_disabled(monkeypatch):
    session = MagicMock()
    child = _child_instance()
    oauth_factory = _real_oauth_factory()

    with patch("ada_backend.services.agent_builder_service.FACTORY_REGISTRY") as mock_registry, \
         patch("ada_backend.services.agent_builder_service.has_oauth_connection", return_value=False) as has_conn:
        mock_registry.get.return_value = oauth_factory
        assert _should_skip_oauth_tool(session, child, skip_flag=False) is False
        has_conn.assert_not_called()


def test_does_not_skip_oauth_tool_when_connection_exists():
    session = MagicMock()
    child = _child_instance()
    oauth_factory = _real_oauth_factory()

    with patch("ada_backend.services.agent_builder_service.FACTORY_REGISTRY") as mock_registry, \
         patch("ada_backend.services.agent_builder_service.has_oauth_connection", return_value=True):
        mock_registry.get.return_value = oauth_factory
        assert _should_skip_oauth_tool(session, child, skip_flag=True) is False


def test_does_not_skip_non_oauth_tool():
    session = MagicMock()
    child = _child_instance()
    non_oauth_factory = MagicMock()

    with patch("ada_backend.services.agent_builder_service.FACTORY_REGISTRY") as mock_registry, \
         patch("ada_backend.services.agent_builder_service.has_oauth_connection") as has_conn:
        mock_registry.get.return_value = non_oauth_factory
        assert _should_skip_oauth_tool(session, child, skip_flag=True) is False
        has_conn.assert_not_called()
