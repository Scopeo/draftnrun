import re
from typing import Union

from engine.field_expressions.ast import ConcatNode, ExpressionNode, JsonBuildNode, LiteralNode, RefNode, VarNode
from engine.field_expressions.errors import FieldExpressionParseError

# Matches @{{instance.port}} (RefNode) or @{{var_name}} (VarNode).
# group(1) = first identifier, group(2) = port (if dot present), group(3) = key (if :: present)
_TOKEN_PATTERN = re.compile(
    r"@\{\{\s*([a-zA-Z0-9_-]+)(?:\.([a-zA-Z0-9_-]+)(?:::([a-zA-Z0-9_-]+))?)?\s*\}\}"
)


# TODO: Use a more robust parser instead of a regex
def parse_expression(expression_text: str) -> ExpressionNode:
    """Parse a raw field expression string into an AST.

    Supported syntax:
      - Plain text -> LiteralNode
      - @{{instance.port}} -> RefNode
      - @{{instance.port::key}} -> RefNode with key extraction
      - Mixed text with multiple refs -> ConcatNode

    Errors:
      - Malformed reference patterns raise FieldExpressionParseError
    """
    if expression_text == "":
        return LiteralNode(value="")

    # Early malformed detection: unbalanced @{{ and }} anywhere in the string
    open_count = expression_text.count("@{{")
    total_close = expression_text.count("}}")
    template_var_count = len(re.findall(r"(?<!@)\{\{[^}]*\}\}", expression_text))
    close_count = total_close - template_var_count
    if open_count != close_count:
        raise FieldExpressionParseError("Unbalanced reference delimiters '@{{' and '}}'")

    parts: list[LiteralNode | RefNode | VarNode] = []
    idx = 0
    for match in _TOKEN_PATTERN.finditer(expression_text):
        start, end = match.span()
        if start > idx:
            # preceding literal
            parts.append(LiteralNode(value=expression_text[idx:start]))
        first, port, key = match.group(1), match.group(2), match.group(3)
        if port is not None:
            parts.append(RefNode(instance=first, port=port, key=key))
        else:
            parts.append(VarNode(name=first))
        idx = end

    # trailing literal
    if idx < len(expression_text):
        parts.append(LiteralNode(value=expression_text[idx:]))

    # If no refs/vars found, return a simple literal node
    if all(isinstance(p, LiteralNode) for p in parts):
        return parts[0] if parts else LiteralNode(value="")

    # Single ref or var — unwrap from concat
    if len(parts) == 1:
        return parts[0]

    return ConcatNode(parts=parts)


def parse_expression_flexible(value: Union[str, dict]) -> ExpressionNode:
    """Parse an expression from either text or JSON format.

    This is a unified entry point that handles both text expressions
    (e.g., "@{{comp.port}}") and JSON/dict structures (e.g., {"type": "ref", ...}).

    Args:
        value: Either a string expression or a dict/JSON structure

    Returns:
        The parsed ExpressionNode

    Raises:
        FieldExpressionParseError: If parsing fails
    """
    if isinstance(value, dict):
        # Import here to avoid circular dependency
        from engine.field_expressions.serializer import from_json

        try:
            return from_json(value)
        except Exception as e:
            raise FieldExpressionParseError(f"Invalid JSON expression structure: {e}") from e
    elif isinstance(value, str):
        return parse_expression(value)
    else:
        raise FieldExpressionParseError(f"Expected str or dict, got {type(value).__name__}: {value!r}")


def unparse_expression(expression: ExpressionNode) -> str:
    """Convert an AST to normalized text using structural pattern matching.

    Note: JsonBuildNode cannot be unparsed to simple text syntax since it represents
    a structured JSON template. It will be rendered as a placeholder.
    """
    match expression:
        case LiteralNode(value=v):
            return v
        case RefNode(instance=i, port=p, key=None):
            return "@{{" + i + "." + p + "}}"
        case RefNode(instance=i, port=p, key=k) if k is not None:
            return "@{{" + i + "." + p + "::" + k + "}}"
        case VarNode(name=n):
            return "@{{" + n + "}}"
        case ConcatNode(parts=parts):
            return "".join(unparse_expression(p) for p in parts)
        case JsonBuildNode():
            return "[JSON_BUILD]"  # Placeholder - cannot represent in simple text
        case _:
            return ""
