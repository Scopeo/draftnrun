from engine.field_expressions.traversal import select_nodes, get_pure_ref
from engine.field_expressions.ast import RefNode
from engine.field_expressions.serde import from_json


def test_refs_and_instances_simple():
    ast = from_json({"type": "ref", "instance": "A", "port": "out"})
    assert [r.instance for r in select_nodes(ast, lambda n: isinstance(n, RefNode))] == ["A"]
    assert get_pure_ref(ast) is not None


def test_is_pure_ref_concat_single_ref_empty_literals():
    ast = from_json(
        {
            "type": "concat",
            "parts": [
                {"type": "literal", "value": ""},
                {"type": "ref", "instance": "B", "port": "x"},
                {"type": "literal", "value": ""},
            ],
        }
    )
    assert get_pure_ref(ast) is not None
    assert {r.instance for r in select_nodes(ast, lambda n: isinstance(n, RefNode))} == {"B"}


def test_is_not_pure_when_multiple_refs_or_nonempty_literal():
    multi = from_json(
        {
            "type": "concat",
            "parts": [
                {"type": "ref", "instance": "A", "port": "o"},
                {"type": "ref", "instance": "B", "port": "p"},
            ],
        }
    )
    assert get_pure_ref(multi) is None

    with_literal = from_json(
        {
            "type": "concat",
            "parts": [
                {"type": "literal", "value": "x"},
                {"type": "ref", "instance": "A", "port": "o"},
            ],
        }
    )
    assert get_pure_ref(with_literal) is None
