import pytest

from ada_backend.services.field_formulas.parser import parse_field_formula
from ada_backend.services.field_formulas.ast import LiteralNode, RefNode, ConcatNode
from ada_backend.services.field_formulas.errors import FieldFormulaParseError


def test_parse_literal_only():
    ast = parse_field_formula("hello world")
    assert isinstance(ast, LiteralNode)
    assert ast.to_dict() == {"type": "literal", "value": "hello world"}


def test_parse_single_ref_only():
    ast = parse_field_formula("@{{comp1.output}}")
    assert isinstance(ast, ConcatNode) or isinstance(ast, RefNode)
    # Our parser returns Concat when mixed parts; for a pure ref we can allow
    # a single ref as concat of one ref or a ref node.
    d = ast.to_dict()
    if d["type"] == "ref":
        assert d == {"type": "ref", "instance": "comp1", "port": "output"}
    else:
        assert d == {
            "type": "concat",
            "parts": [
                {"type": "ref", "instance": "comp1", "port": "output"},
            ],
        }


def test_parse_mixed_literals_and_refs():
    text = "task: @{{comp1.output}}\nstyle: @{{comp2.out}}"
    ast = parse_field_formula(text)
    assert isinstance(ast, ConcatNode)
    assert ast.to_dict() == {
        "type": "concat",
        "parts": [
            {"type": "literal", "value": "task: "},
            {"type": "ref", "instance": "comp1", "port": "output"},
            {"type": "literal", "value": "\nstyle: "},
            {"type": "ref", "instance": "comp2", "port": "out"},
        ],
    }


def test_malformed_unbalanced_delimiters():
    with pytest.raises(FieldFormulaParseError):
        parse_field_formula("hello @{{comp.out}")
