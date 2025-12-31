import pytest

from engine.field_expressions.ast import ConcatNode, LiteralNode, RefNode
from engine.field_expressions.errors import FieldExpressionParseError
from engine.field_expressions.parser import parse_expression, unparse_expression
from engine.field_expressions.serializer import from_json, to_json


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
    # unparse should format to match parser input (double braces)
    assert unparse_expression(ast2) == "@{{comp1.output}}"


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
    assert unparse_expression(ast2) == "task: @{{comp1.output}}\nstyle: @{{comp2.out}}"


def test_malformed_unbalanced_delimiters():
    with pytest.raises(FieldExpressionParseError):
        parse_expression("hello @{{comp.out}")


def test_parse_ref_with_key():
    ast = parse_expression("@{{comp1.output::messages}}")
    assert isinstance(ast, ConcatNode) or isinstance(ast, RefNode)
    # Parser returns ConcatNode even for single refs
    if isinstance(ast, ConcatNode):
        assert len(ast.parts) == 1
        ref_node = ast.parts[0]
        assert isinstance(ref_node, RefNode)
        assert ref_node.instance == "comp1"
        assert ref_node.port == "output"
        assert ref_node.key == "messages"
    else:
        assert ast.instance == "comp1"
        assert ast.port == "output"
        assert ast.key == "messages"

    # serde roundtrip
    j = to_json(ast)
    if j["type"] == "ref":
        assert j == {"type": "ref", "instance": "comp1", "port": "output", "key": "messages"}
    else:
        assert j == {
            "type": "concat",
            "parts": [
                {"type": "ref", "instance": "comp1", "port": "output", "key": "messages"},
            ],
        }
    ast2 = from_json(j)

    # unparse roundtrip
    unparsed = unparse_expression(ast2)
    assert unparsed == "@{{comp1.output::messages}}"


def test_parse_ref_without_key():
    ast = parse_expression("@{{comp1.output}}")
    assert isinstance(ast, ConcatNode) or isinstance(ast, RefNode)
    # Parser returns ConcatNode even for single refs
    if isinstance(ast, ConcatNode):
        assert len(ast.parts) == 1
        ref_node = ast.parts[0]
        assert isinstance(ref_node, RefNode)
        assert ref_node.instance == "comp1"
        assert ref_node.port == "output"
        assert ref_node.key is None
    else:
        assert ast.instance == "comp1"
        assert ast.port == "output"
        assert ast.key is None


def test_parse_concat_with_key():
    text = "prefix: @{{comp1.output::key}} suffix"
    ast = parse_expression(text)
    assert isinstance(ast, ConcatNode)
    parts_json = to_json(ast)["parts"]
    ref_part = [p for p in parts_json if p["type"] == "ref"][0]
    assert ref_part == {"type": "ref", "instance": "comp1", "port": "output", "key": "key"}

    # unparse preserves key
    unparsed = unparse_expression(ast)
    assert unparsed == "prefix: @{{comp1.output::key}} suffix"
