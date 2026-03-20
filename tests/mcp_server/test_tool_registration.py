import pytest

from mcp_server.tools import context_tools, register_all_tools


def test_register_all_tools_reports_failing_module(monkeypatch):
    def boom(_mcp):
        raise ValueError("broken module")

    monkeypatch.setattr(context_tools, "register", boom)

    with pytest.raises(RuntimeError, match="context_tools") as exc_info:
        register_all_tools(object())

    assert isinstance(exc_info.value.__cause__, ValueError)
