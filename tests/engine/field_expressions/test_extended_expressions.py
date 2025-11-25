import pytest
from engine.field_expressions.ast import ExternalRefNode, LiteralNode, ConcatNode
from engine.field_expressions.parser import parse_expression, unparse_expression
from engine.graph_runner.field_expression_management import evaluate_expression
from engine.field_expressions.errors import FieldExpressionError, FieldExpressionParseError
from engine.field_expressions.traversal import get_pure_ref

class TestExtendedFieldExpressions:
    def test_parse_external_ref(self):
        """Test parsing of external references."""
        # Simple external ref
        expr = parse_expression("@{ $settings.api_key }")
        assert isinstance(expr, ExternalRefNode)
        assert expr.source == "settings"
        assert expr.key == "api_key"

        # Another source
        expr = parse_expression("@{ $secrets.password }")
        assert isinstance(expr, ExternalRefNode)
        assert expr.source == "secrets"
        assert expr.key == "password"

    def test_parse_mixed_expressions(self):
        """Test parsing mixed literals, refs, and external refs."""
        text = "Key: @{ $settings.key }, Value: @{{comp.out}}"
        expr = parse_expression(text)
        
        assert isinstance(expr, ConcatNode)
        assert len(expr.parts) == 4
        assert isinstance(expr.parts[0], LiteralNode)
        assert expr.parts[0].value == "Key: "
        assert isinstance(expr.parts[1], ExternalRefNode)
        assert expr.parts[1].source == "settings"
        assert expr.parts[1].key == "key"
        assert isinstance(expr.parts[2], LiteralNode)
        assert expr.parts[2].value == ", Value: "
        assert expr.parts[3].instance == "comp"
        assert expr.parts[3].port == "out"

    def test_unparse_external_ref(self):
        """Test converting AST back to string."""
        node = ExternalRefNode(source="env", key="VAR")
        assert unparse_expression(node) == "@{ $env.VAR }"

    def test_evaluate_external_ref(self):
        """Test evaluating external references with context."""
        expr = ExternalRefNode(source="settings", key="theme")
        context = {
            "settings": {"theme": "dark"},
            "secrets": {"token": "123"}
        }
        
        result = evaluate_expression(expr, "test_field", {}, external_context=context)
        assert result == "dark"

    def test_evaluate_missing_context(self):
        """Test error when context is missing."""
        expr = ExternalRefNode(source="settings", key="theme")
        
        with pytest.raises(FieldExpressionError) as exc:
            evaluate_expression(expr, "test_field", {})
        assert "External context missing" in str(exc.value)

    def test_evaluate_missing_source(self):
        """Test error when source is missing in context."""
        expr = ExternalRefNode(source="missing", key="key")
        context = {"settings": {}}
        
        with pytest.raises(FieldExpressionError) as exc:
            evaluate_expression(expr, "test_field", {}, external_context=context)
        assert "External source 'missing' not found" in str(exc.value)

    def test_evaluate_missing_key(self):
        """Test error when key is missing in source."""
        expr = ExternalRefNode(source="settings", key="missing")
        context = {"settings": {"present": "val"}}
        
        with pytest.raises(FieldExpressionError) as exc:
            evaluate_expression(expr, "test_field", {}, external_context=context)
        assert "Key 'missing' not found" in str(exc.value)

    def test_get_pure_ref_external(self):
        """Test that ExternalRefNode is NOT considered a pure ref."""
        expr = ExternalRefNode(source="settings", key="key")
        assert get_pure_ref(expr) is None

        # Even if wrapped in Concat
        concat = ConcatNode(parts=[expr])
        assert get_pure_ref(concat) is None
