import re

from engine.field_expressions.ast import ConcatNode, LiteralNode, RefNode, ExpressionNode, VarNode, VarType
from engine.field_expressions.errors import FieldExpressionParseError

# Matches @{{instance.port}} where instance and port allow [a-zA-Z0-9_-]. An optional key can be provided after ::.
_REF_PATTERN = re.compile(r"@\{\{\s*([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_-]+)(?:::([a-zA-Z0-9_-]+))?\s*\}\}")

# Matches ${{var_type.key}} where var_type is a VarType value and key is typically a UUID.
_VAR_PATTERN = re.compile(r"\$\{\{\s*([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_-]+)\s*\}\}")

# Valid var_type values (from VarType enum)
_VALID_VAR_TYPES = {v.value for v in VarType}


# TODO: Use a more robust parser instead of a regex
def parse_expression(expression_text: str) -> ExpressionNode:
    """Parse a raw field expression string into an AST.

    Supported syntax:
      - Plain text -> LiteralNode
      - @{{instance.port}} -> RefNode
      - @{{instance.port::key}} -> RefNode with key extraction
      - ${{var_type.id}} -> VarNode (e.g. ${{secrets.550e8400-...}})
      - Mixed text with multiple refs -> ConcatNode

    Errors:
      - Malformed reference patterns raise FieldExpressionParseError
      - Invalid var_type raises FieldExpressionParseError
    """
    if expression_text == "":
        return LiteralNode(value="")

    # Early malformed detection: unbalanced @{{ or ${{ and }} anywhere in the string
    ref_open_count = expression_text.count("@{{")
    var_open_count = expression_text.count("${{")
    close_count = expression_text.count("}}")
    if ref_open_count + var_open_count != close_count:
        raise FieldExpressionParseError("Unbalanced expression delimiters '@{{'/'${{' and '}}'")

    parts: list[LiteralNode | RefNode | VarNode] = []
    idx = 0

    # Combine both patterns to find all matches in order
    # We'll use a simple approach: find all matches for both, sort by position, and iterate
    # Or better: iterate through the string and check which pattern matches next

    # Actually, let's use a single combined regex for iteration to ensure correct ordering
    # But since the syntax is distinct (@{{ vs ${{), we can just search for @ or $ and see what follows

    # Let's stick to the current structure but handle both.
    # Since we need to preserve order, we can find all matches from both patterns and sort them.

    matches = []
    for match in _REF_PATTERN.finditer(expression_text):
        matches.append((match.start(), match.end(), match, "ref"))
    for match in _VAR_PATTERN.finditer(expression_text):
        matches.append((match.start(), match.end(), match, "var"))

    matches.sort(key=lambda x: x[0])

    for start, end, match, type_ in matches:
        if start < idx:
            # Overlapping match (shouldn't happen with well-formed distinct syntax)
            continue

        if start > idx:
            # preceding literal
            parts.append(LiteralNode(value=expression_text[idx:start]))

        if type_ == "ref":
            instance, port = match.group(1), match.group(2)
            key: str | None = match.group(3)
            parts.append(RefNode(instance=instance, port=port, key=key))
        else:  # type_ == "var"
            var_type_str, key = match.group(1), match.group(2)
            if var_type_str not in _VALID_VAR_TYPES:
                raise FieldExpressionParseError(
                    f"Invalid variable type '{var_type_str}'. Valid types: {list(_VALID_VAR_TYPES)}"
                )
            parts.append(VarNode(var_type=VarType(var_type_str), key=key))

        idx = end

    # trailing literal
    if idx < len(expression_text):
        parts.append(LiteralNode(value=expression_text[idx:]))

    # If no refs found, return a simple literal node
    if not parts:
        return LiteralNode(value="")

    if len(parts) == 1:
        return parts[0]

    return ConcatNode(parts=parts)


def unparse_expression(expression: ExpressionNode) -> str:
    """Convert an AST to normalized text using structural pattern matching."""
    match expression:
        case LiteralNode(value=v):
            return v
        case RefNode(instance=i, port=p, key=None):
            return "@{{" + i + "." + p + "}}"
        case RefNode(instance=i, port=p, key=k) if k is not None:
            return "@{{" + i + "." + p + "::" + k + "}}"
        case VarNode(var_type=vt, key=k):
            return "${{" + vt.value + "." + k + "}}"
        case ConcatNode(parts=parts):
            return "".join(unparse_expression(p) for p in parts)
        case _:
            return ""
