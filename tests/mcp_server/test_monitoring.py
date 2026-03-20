"""Monitoring tools coverage tests."""

from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import monitoring
from mcp_server.tools.monitoring import _normalize_duration


class TestNormalizeDuration:
    def test_clamps_to_min(self):
        assert _normalize_duration(0) == 1

    def test_clamps_to_max(self):
        assert _normalize_duration(500) == 365

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

    def test_get_credit_usage_is_org_scoped(self):
        spec = next(s for s in monitoring.PROXY_SPECS if s.name == "get_credit_usage")
        assert spec.scope == "org"


@pytest.mark.asyncio
async def test_list_traces_caps_page_size(fake_mcp, monkeypatch):
    get_mock = AsyncMock(return_value={"traces": []})
    monkeypatch.setattr(monitoring, "_get_auth", lambda: ("jwt", "user-1"))
    monkeypatch.setattr(monitoring, "api", type("API", (), {"get": get_mock})())

    monitoring.register(fake_mcp)
    await fake_mcp.tools["list_traces"](project_id="p-1", page_size=999)

    assert get_mock.call_args.kwargs["page_size"] == 100


@pytest.mark.asyncio
async def test_list_traces_rejects_zero_page(fake_mcp, monkeypatch):
    monkeypatch.setattr(monitoring, "_get_auth", lambda: ("jwt", "user-1"))
    monitoring.register(fake_mcp)

    with pytest.raises(ValueError, match="page must be >= 1"):
        await fake_mcp.tools["list_traces"](project_id="p-1", page=0)
