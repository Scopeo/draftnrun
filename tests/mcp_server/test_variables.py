"""Variables tools coverage tests."""

import pytest

from mcp_server.tools import variables

ALL_TOOL_NAMES = [
    "list_variable_definitions", "upsert_variable_definition", "delete_variable_definition",
    "list_variable_sets", "upsert_variable_set", "delete_variable_set",
    "list_secrets", "upsert_secret", "delete_secret",
]


class TestVariableSpecs:
    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_all_require_admin_role(self, tool_name):
        spec = next(s for s in variables.SPECS if s.name == tool_name)
        assert spec.scope == "role"
        assert "admin" in spec.roles
        assert "super_admin" in spec.roles

    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_all_use_org_id_path(self, tool_name):
        spec = next(s for s in variables.SPECS if s.name == tool_name)
        assert "{org_id}" in spec.path
