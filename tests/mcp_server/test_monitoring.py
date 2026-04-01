"""Monitoring tools coverage tests."""

from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory, monitoring
from mcp_server.tools.monitoring import _normalize_duration
from tests.mcp_server.conftest import FAKE_OTEL_TRACE_ID, FAKE_PROJECT_ID


class TestNormalizeDuration:
    def test_clamps_to_min(self):
        assert _normalize_duration(0) == 1

    def test_clamps_to_max(self):
        assert _normalize_duration(500) == 90

    def test_passes_valid(self):
        assert _normalize_duration(30) == 30

    def test_rejects_boolean(self):
        with pytest.raises(ValueError, match="integer"):
            _normalize_duration(True)

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="integer"):
            _normalize_duration("abc")


class TestMonitoringSpecs:
    def test_get_trace_tree_is_auth_only(self):
        spec = next(s for s in monitoring.PROXY_SPECS if s.name == "get_trace_tree")
        assert spec.scope == "auth"
        assert spec.method == "get"

    def test_get_trace_tree_trace_id_is_str(self):
        spec = next(s for s in monitoring.PROXY_SPECS if s.name == "get_trace_tree")
        trace_param = next(p for p in spec.path_params if p.name == "trace_id")
        assert trace_param.annotation is str

    def test_get_credit_usage_is_org_scoped(self):
        spec = next(s for s in monitoring.PROXY_SPECS if s.name == "get_credit_usage")
        assert spec.scope == "org"


@pytest.mark.asyncio
async def test_get_trace_tree_accepts_otel_hex_id(fake_mcp, monkeypatch):
    get_mock = AsyncMock(return_value={"spans": []})
    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt", "user-1"))
    monkeypatch.setattr(_factory.api, "get", get_mock)

    monitoring.register(fake_mcp)
    await fake_mcp.tools["get_trace_tree"](trace_id=FAKE_OTEL_TRACE_ID)

    called_path = get_mock.call_args.args[0]
    assert FAKE_OTEL_TRACE_ID in called_path


@pytest.mark.asyncio
async def test_list_traces_caps_page_size(fake_mcp, monkeypatch):
    get_mock = AsyncMock(return_value={"traces": []})
    monkeypatch.setattr(monitoring, "_get_auth", lambda: ("jwt", "user-1"))
    monkeypatch.setattr(monitoring, "api", type("API", (), {"get": get_mock})())

    monitoring.register(fake_mcp)
    await fake_mcp.tools["list_traces"](project_id=FAKE_PROJECT_ID, page_size=999)

    assert get_mock.call_args.kwargs["page_size"] == 100


@pytest.mark.asyncio
async def test_list_traces_passes_default_duration(fake_mcp, monkeypatch):
    get_mock = AsyncMock(return_value={"traces": []})
    monkeypatch.setattr(monitoring, "_get_auth", lambda: ("jwt", "user-1"))
    monkeypatch.setattr(monitoring, "api", type("API", (), {"get": get_mock})())

    monitoring.register(fake_mcp)
    await fake_mcp.tools["list_traces"](project_id=FAKE_PROJECT_ID)

    assert get_mock.call_args.kwargs["duration"] == 30


@pytest.mark.asyncio
async def test_list_traces_normalizes_duration(fake_mcp, monkeypatch):
    get_mock = AsyncMock(return_value={"traces": []})
    monkeypatch.setattr(monitoring, "_get_auth", lambda: ("jwt", "user-1"))
    monkeypatch.setattr(monitoring, "api", type("API", (), {"get": get_mock})())

    monitoring.register(fake_mcp)
    await fake_mcp.tools["list_traces"](project_id=FAKE_PROJECT_ID, duration=9999)

    assert get_mock.call_args.kwargs["duration"] == 90


@pytest.mark.asyncio
async def test_list_traces_rejects_zero_page(fake_mcp, monkeypatch):
    monkeypatch.setattr(monitoring, "_get_auth", lambda: ("jwt", "user-1"))
    monitoring.register(fake_mcp)

    with pytest.raises(ValueError, match="page must be >= 1"):
        await fake_mcp.tools["list_traces"](project_id=FAKE_PROJECT_ID, page=0)
