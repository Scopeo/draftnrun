import pytest
from engine.field_expressions.ast import VarNode, VarType, LiteralNode, ConcatNode
from engine.field_expressions.parser import parse_expression, unparse_expression
from engine.graph_runner.field_expression_management import evaluate_expression
from engine.field_expressions.errors import FieldExpressionError, FieldExpressionParseError
from engine.field_expressions.traversal import get_pure_ref


class TestExtendedFieldExpressions:
    def test_parse_var_node(self):
        """Test parsing of variable injections."""
        # Parse with secrets var_type
        expr = parse_expression("@{ $secrets.550e8400-e29b-41d4-a716-446655440000 }")
        assert isinstance(expr, VarNode)
        assert expr.var_type == VarType.SECRETS
        assert expr.key == "550e8400-e29b-41d4-a716-446655440000"

    def test_parse_invalid_var_type(self):
        """Test that invalid var_type raises error."""
        with pytest.raises(FieldExpressionParseError) as exc:
            parse_expression("@{ $invalid.key }")
        assert "Invalid variable type" in str(exc.value)

    def test_parse_mixed_expressions(self):
        """Test parsing mixed literals, refs, and var nodes."""
        text = "Secret: @{ $secrets.abc-123 }, Value: @{{comp.out}}"
        expr = parse_expression(text)

        assert isinstance(expr, ConcatNode)
        assert len(expr.parts) == 4
        assert isinstance(expr.parts[0], LiteralNode)
        assert expr.parts[0].value == "Secret: "
        assert isinstance(expr.parts[1], VarNode)
        assert expr.parts[1].var_type == VarType.SECRETS
        assert expr.parts[1].key == "abc-123"
        assert isinstance(expr.parts[2], LiteralNode)
        assert expr.parts[2].value == ", Value: "
        assert expr.parts[3].instance == "comp"
        assert expr.parts[3].port == "out"

    def test_unparse_var_node(self):
        """Test converting AST back to string."""
        node = VarNode(var_type=VarType.SECRETS, key="abc-123")
        assert unparse_expression(node) == "@{ $secrets.abc-123 }"

    def test_evaluate_var_node(self):
        """Test evaluating variable injections with inject_vars."""
        expr = VarNode(var_type=VarType.SECRETS, key="secret-uuid")
        inject_vars = {
            VarType.SECRETS: {"secret-uuid": "my-secret-value"},
        }

        result = evaluate_expression(expr, "test_field", {}, inject_vars=inject_vars)
        assert result == "my-secret-value"

    def test_evaluate_missing_inject_vars(self):
        """Test error when inject_vars is missing."""
        expr = VarNode(var_type=VarType.SECRETS, key="secret-uuid")

        with pytest.raises(FieldExpressionError) as exc:
            evaluate_expression(expr, "test_field", {})
        assert "Injected variables missing" in str(exc.value)

    def test_evaluate_missing_var_type(self):
        """Test error when var_type is missing in inject_vars."""
        expr = VarNode(var_type=VarType.SECRETS, key="key")
        inject_vars: dict[VarType, dict[str, str]] = {}

        with pytest.raises(FieldExpressionError) as exc:
            evaluate_expression(expr, "test_field", {}, inject_vars=inject_vars)
        assert "Variable type 'secrets' not found" in str(exc.value)

    def test_evaluate_missing_key(self):
        """Test error when key is missing in var_type."""
        expr = VarNode(var_type=VarType.SECRETS, key="missing-uuid")
        inject_vars = {
            VarType.SECRETS: {"other-uuid": "val"},
        }

        with pytest.raises(FieldExpressionError) as exc:
            evaluate_expression(expr, "test_field", {}, inject_vars=inject_vars)
        assert "Key 'missing-uuid' not found" in str(exc.value)

    def test_get_pure_ref_var_node(self):
        """Test that VarNode is NOT considered a pure ref."""
        expr = VarNode(var_type=VarType.SECRETS, key="key")
        assert get_pure_ref(expr) is None

        # Even if wrapped in Concat
        concat = ConcatNode(parts=[expr])
        assert get_pure_ref(concat) is None
