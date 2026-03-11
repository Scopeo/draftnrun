from engine.llm_services.utils import resolve_schema_refs, resolve_tool_refs


class TestResolveSchemaRefs:
    def test_no_refs_passthrough(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }
        assert resolve_schema_refs(schema) == schema

    def test_simple_ref_is_inlined(self):
        schema = {
            "type": "object",
            "properties": {
                "address": {"$ref": "#/$defs/Address"},
            },
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                    },
                }
            },
        }
        result = resolve_schema_refs(schema)
        assert "$defs" not in result
        assert "$ref" not in result["properties"]["address"]
        assert result["properties"]["address"]["type"] == "object"
        assert "street" in result["properties"]["address"]["properties"]

    def test_nested_refs_are_resolved(self):
        schema = {
            "type": "object",
            "properties": {
                "filters": {"$ref": "#/$defs/Filters"},
            },
            "$defs": {
                "DateCondition": {
                    "type": "object",
                    "properties": {
                        "range": {"type": "string"},
                    },
                },
                "Filters": {
                    "type": "object",
                    "properties": {
                        "date": {"$ref": "#/$defs/DateCondition"},
                    },
                },
            },
        }
        result = resolve_schema_refs(schema)
        assert "$defs" not in result
        date_prop = result["properties"]["filters"]["properties"]["date"]
        assert "$ref" not in date_prop
        assert date_prop["type"] == "object"
        assert date_prop["properties"]["range"]["type"] == "string"

    def test_ref_in_array_items(self):
        schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Tag"},
                },
            },
            "$defs": {
                "Tag": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
        }
        result = resolve_schema_refs(schema)
        assert "$defs" not in result
        items = result["properties"]["tags"]["items"]
        assert "$ref" not in items
        assert items["type"] == "object"

    def test_ref_with_sibling_keys_merges(self):
        """Sibling keys alongside $ref should override the referenced schema."""
        schema = {
            "type": "object",
            "properties": {
                "item": {
                    "$ref": "#/$defs/Base",
                    "description": "overridden",
                },
            },
            "$defs": {
                "Base": {
                    "type": "string",
                    "description": "original",
                }
            },
        }
        result = resolve_schema_refs(schema)
        prop = result["properties"]["item"]
        assert prop["type"] == "string"
        assert prop["description"] == "overridden"

    def test_does_not_mutate_original(self):
        schema = {
            "type": "object",
            "properties": {"a": {"$ref": "#/$defs/A"}},
            "$defs": {"A": {"type": "integer"}},
        }
        original_defs = schema["$defs"].copy()
        resolve_schema_refs(schema)
        assert "$defs" in schema
        assert schema["$defs"] == original_defs

    def test_empty_defs(self):
        schema = {"type": "object", "$defs": {}}
        result = resolve_schema_refs(schema)
        assert result == {"type": "object"}

    def test_anyof_with_refs(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {
                    "anyOf": [
                        {"$ref": "#/$defs/TypeA"},
                        {"$ref": "#/$defs/TypeB"},
                    ]
                }
            },
            "$defs": {
                "TypeA": {"type": "string"},
                "TypeB": {"type": "integer"},
            },
        }
        result = resolve_schema_refs(schema)
        any_of = result["properties"]["value"]["anyOf"]
        assert any_of[0] == {"type": "string"}
        assert any_of[1] == {"type": "integer"}

    def test_case_mismatched_ref_is_resolved(self):
        """$ref with wrong casing should still resolve via case-insensitive fallback."""
        schema = {
            "type": "object",
            "properties": {
                "date": {"$ref": "#/$defs/dateCondition"},
            },
            "$defs": {
                "DateCondition": {
                    "type": "object",
                    "properties": {"range": {"type": "string"}},
                }
            },
        }
        result = resolve_schema_refs(schema)
        assert "$defs" not in result
        assert "$ref" not in result["properties"]["date"]
        assert result["properties"]["date"]["type"] == "object"
        assert result["properties"]["date"]["properties"]["range"] == {"type": "string"}


class TestResolveToolRefs:
    def test_resolves_tool_parameters(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "filters": {"$ref": "#/$defs/Filters"},
                        },
                        "$defs": {
                            "Filters": {
                                "type": "object",
                                "properties": {"tag": {"type": "string"}},
                            }
                        },
                    },
                },
            }
        ]
        result = resolve_tool_refs(tools)
        params = result[0]["function"]["parameters"]
        assert "$defs" not in params
        assert params["properties"]["filters"]["type"] == "object"

    def test_does_not_mutate_original_tools(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test",
                    "parameters": {
                        "type": "object",
                        "properties": {"x": {"$ref": "#/$defs/X"}},
                        "$defs": {"X": {"type": "string"}},
                    },
                },
            }
        ]
        resolve_tool_refs(tools)
        assert "$defs" in tools[0]["function"]["parameters"]

    def test_tool_without_parameters(self):
        tools = [
            {
                "type": "function",
                "function": {"name": "noop", "description": "No params"},
            }
        ]
        result = resolve_tool_refs(tools)
        assert result[0]["function"]["name"] == "noop"
