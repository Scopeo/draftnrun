import re

from ada_backend.services.field_formulas.ast import ConcatNode, LiteralNode, RefNode, FormulaNode
from ada_backend.services.field_formulas.errors import FieldFormulaParseError

# Matches @{{instance.port}} where instance and port allow [a-zA-Z0-9_-]
_REF_PATTERN = re.compile(r"@\{\{\s*([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_]+)\s*\}\}")


def parse_field_formula(formula_text: str) -> FormulaNode:
    """Parse a raw field formula string into an AST.

    Supported syntax:
      - Plain text -> LiteralNode
      - {{instance.port}} -> RefNode
      - Mixed text with multiple refs -> ConcatNode

    Errors:
      - Malformed reference patterns raise FieldFormulaParseError
    """
    if formula_text == "":
        return LiteralNode(value="")

    # Early malformed detection: unbalanced @{{ and }} anywhere in the string
    open_count = formula_text.count("@{{")
    close_count = formula_text.count("}}")
    if open_count != close_count:
        raise FieldFormulaParseError("Unbalanced reference delimiters '@{{' and '}}'")

    parts: list[LiteralNode | RefNode] = []
    idx = 0
    for match in _REF_PATTERN.finditer(formula_text):
        start, end = match.span()
        if start > idx:
            # preceding literal
            parts.append(LiteralNode(value=formula_text[idx:start]))
        instance, port = match.group(1), match.group(2)
        parts.append(RefNode(instance=instance, port=port))
        idx = end

    # trailing literal
    if idx < len(formula_text):
        parts.append(LiteralNode(value=formula_text[idx:]))

    # If no refs found, return a simple literal node
    if all(isinstance(p, LiteralNode) for p in parts):
        return parts[0] if parts else LiteralNode(value="")

    return ConcatNode(parts=parts)
