import pytest

from engine.components.sql.sql_tool import SQLTool


class TestParseIncludeTables:
    def test_comma_separated(self):
        assert SQLTool._parse_include_tables("users, orders, products") == ["users", "orders", "products"]

    def test_space_separated(self):
        assert SQLTool._parse_include_tables("users orders products") == ["users", "orders", "products"]

    def test_mixed_separators(self):
        assert SQLTool._parse_include_tables("users,  orders , products") == ["users", "orders", "products"]

    def test_single_table(self):
        assert SQLTool._parse_include_tables("users") == ["users"]

    def test_empty_string(self):
        assert SQLTool._parse_include_tables("") is None

    def test_whitespace_only(self):
        assert SQLTool._parse_include_tables("   ") is None

    def test_none(self):
        assert SQLTool._parse_include_tables(None) is None

    def test_list_passthrough(self):
        assert SQLTool._parse_include_tables(["users", "orders"]) == ["users", "orders"]

    def test_empty_list(self):
        assert SQLTool._parse_include_tables([]) is None
