import re

from engine.field_expressions.ast import ConcatNode, LiteralNode, RefNode, ExpressionNode
from engine.field_expressions.errors import FieldExpressionParseError

# Matches @{{instance.port}} where instance and port allow [a-zA-Z0-9_-]
_REF_PATTERN = re.compile(r"@\{\{\s*([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_]+)\s*\}\}")


# TODO: Use a more robust parser instead of a regex
def parse_expression(expression_text: str) -> ExpressionNode:
    """Parse a raw field expression string into an AST.

    Supported syntax:
      - Plain text -> LiteralNode
      - {{instance.port}} -> RefNode
      - Mixed text with multiple refs -> ConcatNode

    Errors:
      - Malformed reference patterns raise FieldExpressionParseError
    """
    if expression_text == "":
        return LiteralNode(value="")

    # Early malformed detection: unbalanced @{{ and }} anywhere in the string
    open_count = expression_text.count("@{{")
    close_count = expression_text.count("}}")
    if open_count != close_count:
        raise FieldExpressionParseError("Unbalanced reference delimiters '@{{' and '}}'")

    parts: list[LiteralNode | RefNode] = []
    idx = 0
    for match in _REF_PATTERN.finditer(expression_text):
        start, end = match.span()
        if start > idx:
            # preceding literal
            parts.append(LiteralNode(value=expression_text[idx:start]))
        instance, port = match.group(1), match.group(2)
        parts.append(RefNode(instance=instance, port=port))
        idx = end

    # trailing literal
    if idx < len(expression_text):
        parts.append(LiteralNode(value=expression_text[idx:]))

    # If no refs found, return a simple literal node
    if all(isinstance(p, LiteralNode) for p in parts):
        return parts[0] if parts else LiteralNode(value="")

    return ConcatNode(parts=parts)


def unparse_expression(expression: ExpressionNode) -> str:
    """Convert an AST to normalized text using structural pattern matching."""
    match expression:
        case LiteralNode(value=v):
            return v
        case RefNode(instance=i, port=p):
            return f"@{{{i}.{p}}}"
        case ConcatNode(parts=parts):
            return "".join(unparse_expression(p) for p in parts)
        case _:
            return ""
