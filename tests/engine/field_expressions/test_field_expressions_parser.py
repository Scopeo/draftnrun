import pytest

from engine.field_expressions.parser import parse_expression, unparse_expression
from engine.field_expressions.ast import LiteralNode, RefNode, ConcatNode
from engine.field_expressions.serde import to_json, from_json
from engine.field_expressions.errors import FieldExpressionParseError


def test_parse_literal_only():
    ast = parse_expression("hello world")
    assert isinstance(ast, LiteralNode)
    assert to_json(ast) == {"type": "literal", "value": "hello world"}
    # serde roundtrip
    j = to_json(ast)
    ast2 = from_json(j)
    assert isinstance(ast2, LiteralNode)
    assert unparse_expression(ast2) == "hello world"
    assert unparse_expression(ast2) == "hello world"


def test_parse_single_ref_only():
    ast = parse_expression("@{{comp1.output}}")
    assert isinstance(ast, ConcatNode) or isinstance(ast, RefNode)
    # Our parser returns Concat when mixed parts; for a pure ref we can allow
    # a single ref as concat of one ref or a ref node.
    d = to_json(ast)
    if d["type"] == "ref":
        assert d == {"type": "ref", "instance": "comp1", "port": "output"}
    else:
        assert d == {
            "type": "concat",
            "parts": [
                {"type": "ref", "instance": "comp1", "port": "output"},
            ],
        }
    # serde roundtrip
    j = to_json(ast)
    ast2 = from_json(j)
    # unparse should format to a single ref marker
    assert unparse_expression(ast2) in ("@{comp1.output}", "@{{comp1.output}}".replace("{{", "{").replace("}}", "}"))
    assert unparse_expression(ast2) in ("@{comp1.output}", "@{comp1.output}")


def test_parse_mixed_literals_and_refs():
    text = "task: @{{comp1.output}}\nstyle: @{{comp2.out}}"
    ast = parse_expression(text)
    assert isinstance(ast, ConcatNode)
    assert to_json(ast) == {
        "type": "concat",
        "parts": [
            {"type": "literal", "value": "task: "},
            {"type": "ref", "instance": "comp1", "port": "output"},
            {"type": "literal", "value": "\nstyle: "},
            {"type": "ref", "instance": "comp2", "port": "out"},
        ],
    }
    # serde roundtrip
    j = to_json(ast)
    ast2 = from_json(j)
    assert isinstance(ast2, ConcatNode)
    assert unparse_expression(ast2) == "task: @{comp1.output}\nstyle: @{comp2.out}"
    assert unparse_expression(ast2) == "task: @{comp1.output}\nstyle: @{comp2.out}"


def test_malformed_unbalanced_delimiters():
    with pytest.raises(FieldExpressionParseError):
        parse_expression("hello @{{comp.out}")
