"""Traversal utilities for field expression ASTs (pure, reusable).

Provides small helpers to walk expressions and extract common views without
embedding engine/backend policy.
"""

from collections.abc import Callable, Iterator

from engine.field_expressions.ast import ExpressionNode, LiteralNode, RefNode, ConcatNode


def walk(expr: ExpressionNode) -> Iterator[ExpressionNode]:
    """Yield nodes in pre-order."""
    yield expr
    match expr:
        case ConcatNode(parts=parts):
            for p in parts:
                yield from walk(p)
        case _:
            return


def select_nodes(
    expr: ExpressionNode,
    predicate: Callable[[ExpressionNode], bool],
) -> Iterator[ExpressionNode]:
    """Generic selector: yield nodes matching predicate (pre-order)."""
    for node in walk(expr):
        if predicate(node):
            yield node


def get_pure_ref(expr: ExpressionNode) -> RefNode | None:
    """Return the single RefNode if the expression semantically represents exactly one reference.

    A "pure ref" is 1-1 mappable to a port mapping (e.g., "@{{instance.port}}").
    Accepted forms:
      - RefNode(instance, port)
      - ConcatNode with exactly one RefNode and all other parts as empty literals ("")
    Any other structure (multiple refs, non-empty literals, or other node kinds) returns None.
    => is_pure_ref(expr) == (get_pure_ref(expr) is not None)
    """
    if isinstance(expr, RefNode):
        return expr
    if isinstance(expr, ConcatNode):
        ref_node: RefNode | None = None
        for part in expr.parts:
            if isinstance(part, RefNode):
                if ref_node is not None:
                    return None  # more than one ref
                ref_node = part
            elif isinstance(part, LiteralNode):
                if part.value not in (None, ""):
                    return None
            else:
                return None
        return ref_node
    return None
