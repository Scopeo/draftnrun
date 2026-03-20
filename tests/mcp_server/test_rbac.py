"""RBAC hardening regression tests."""


import pytest

from mcp_server.tools import _factory, agents, crons


@pytest.fixture
def _patch_auth(monkeypatch):
    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt", "user-123"))
    monkeypatch.setattr(agents, "_get_auth", lambda: ("jwt", "user-123"))


class TestCreateAgentRole:
    """create_agent must require developer role."""

    @pytest.mark.asyncio
    async def test_rejects_member_role(self, fake_mcp, monkeypatch, _patch_auth):
        async def reject_role(*args, **kwargs):
            raise ValueError("Requires developer role")

        monkeypatch.setattr(agents, "require_role", reject_role)
        agents.register(fake_mcp)

        with pytest.raises(ValueError, match="developer"):
            await fake_mcp.tools["create_agent"](name="test")


class TestCronWriteRoles:
    """Cron write specs must declare developer role scope."""

    @pytest.mark.parametrize("tool_name", [
        "create_cron", "update_cron", "delete_cron", "pause_cron", "resume_cron",
    ])
    def test_cron_write_specs_require_developer_role(self, tool_name):
        spec = next(s for s in crons.SPECS if s.name == tool_name)
        assert spec.scope == "role"
        assert "developer" in spec.roles

    @pytest.mark.parametrize("tool_name", [
        "list_crons", "get_cron", "get_cron_runs",
    ])
    def test_cron_read_specs_remain_org_scoped(self, tool_name):
        spec = next(s for s in crons.SPECS if s.name == tool_name)
        assert spec.scope == "org"
