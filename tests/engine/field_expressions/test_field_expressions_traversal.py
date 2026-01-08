from engine.field_expressions.ast import ConcatNode, LiteralNode, RefNode
from engine.field_expressions.traversal import map_expression


def test_map_expression_literal_unchanged():
    expr = LiteralNode(value="hello")
    result = map_expression(expr, lambda n: n)
    assert result == expr
    assert isinstance(result, LiteralNode)
    assert result.value == "hello"


def test_map_expression_ref_unchanged():
    expr = RefNode(instance="inst1", port="output")
    result = map_expression(expr, lambda n: n)
    assert result == expr
    assert isinstance(result, RefNode)
    assert result.instance == "inst1"
    assert result.port == "output"


def test_map_expression_ref_transform():
    expr = RefNode(instance="old_id", port="output", key="docs")

    def transform(node):
        if isinstance(node, RefNode):
            return RefNode(instance="new_id", port=node.port, key=node.key)
        return node

    result = map_expression(expr, transform)
    assert isinstance(result, RefNode)
    assert result.instance == "new_id"
    assert result.port == "output"
    assert result.key == "docs"


def test_map_expression_concat_unchanged():
    expr = ConcatNode(
        parts=[
            LiteralNode(value="Task: "),
            RefNode(instance="inst1", port="output"),
            LiteralNode(value=" - Style: "),
            RefNode(instance="inst1", port="output"),
        ]
    )
    result = map_expression(expr, lambda n: n)
    assert isinstance(result, ConcatNode)
    assert len(result.parts) == 4
    assert result.parts[0].value == "Task: "
    assert result.parts[1].instance == "inst1"


def test_map_expression_concat_remap_refs():
    expr = ConcatNode(
        parts=[
            LiteralNode(value="Task: "),
            RefNode(instance="old_id", port="output"),
            LiteralNode(value=" - Sources: "),
            RefNode(instance="old_id", port="artifacts", key="docs"),
        ]
    )

    def transform(node):
        if isinstance(node, RefNode) and node.instance == "old_id":
            return RefNode(instance="new_id", port=node.port, key=node.key)
        return node

    result = map_expression(expr, transform)
    assert isinstance(result, ConcatNode)
    assert len(result.parts) == 4
    assert isinstance(result.parts[0], LiteralNode)
    assert result.parts[0].value == "Task: "
    assert isinstance(result.parts[1], RefNode)
    assert result.parts[1].instance == "new_id"
    assert result.parts[1].port == "output"
    assert isinstance(result.parts[2], LiteralNode)
    assert result.parts[2].value == " - Sources: "
    assert isinstance(result.parts[3], RefNode)
    assert result.parts[3].instance == "new_id"
    assert result.parts[3].port == "artifacts"
    assert result.parts[3].key == "docs"


def test_map_expression_nested_concat():
    inner = ConcatNode(
        parts=[
            LiteralNode(value="inner: "),
            RefNode(instance="old_id", port="output"),
        ]
    )
    expr = ConcatNode(
        parts=[
            LiteralNode(value="outer: "),
            inner,
        ]
    )

    def transform(node):
        if isinstance(node, RefNode) and node.instance == "old_id":
            return RefNode(instance="new_id", port=node.port, key=node.key)
        return node

    result = map_expression(expr, transform)
    assert isinstance(result, ConcatNode)
    assert len(result.parts) == 2
    assert isinstance(result.parts[0], LiteralNode)
    assert isinstance(result.parts[1], ConcatNode)
    inner_result = result.parts[1]
    assert len(inner_result.parts) == 2
    assert isinstance(inner_result.parts[1], RefNode)
    assert inner_result.parts[1].instance == "new_id"


def test_map_expression_selective_transform():
    expr = ConcatNode(
        parts=[
            RefNode(instance="keep_me", port="output"),
            RefNode(instance="change_me", port="output"),
        ]
    )

    def transform(node):
        if isinstance(node, RefNode) and node.instance == "change_me":
            return RefNode(instance="changed", port=node.port, key=node.key)
        return node

    result = map_expression(expr, transform)
    assert isinstance(result, ConcatNode)
    assert result.parts[0].instance == "keep_me"
    assert result.parts[1].instance == "changed"
