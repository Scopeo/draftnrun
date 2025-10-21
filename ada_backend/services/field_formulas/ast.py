"""AST nodes for field formulas."""

from dataclasses import dataclass
from typing import Any, Dict, List, Union


@dataclass(frozen=True)
class LiteralNode:
    """Literal value node."""

    value: str

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "literal", "value": self.value}


@dataclass(frozen=True)
class RefNode:
    """Reference to another component's output."""

    instance: str
    port: str

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "ref", "instance": self.instance, "port": self.port}


@dataclass(frozen=True)
class ConcatNode:
    """Concatenation of literal and ref parts."""

    parts: List[Union[LiteralNode, RefNode]]

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "concat", "parts": [part.to_dict() for part in self.parts]}


FormulaNode = Union[LiteralNode, RefNode, ConcatNode]


def unparse_formula_dict(ast_dict: Dict[str, Any]) -> str:
    """Convert a stored formula_json back to a text form for UI.

    This mirrors the parser rules and reconstructs a normalized string like:
    "literal @{{instance.port}} more literal".
    TODO: Done like this for now because DB stores the AST as a JSONB and
    it doesn't hydrate the AST objects. Check if we can improve this.
    """
    t = ast_dict.get("type")
    if t == "literal":
        return ast_dict.get("value", "")
    if t == "ref":
        instance = ast_dict.get("instance", "")
        port = ast_dict.get("port", "")
        return f"@{{{instance}.{port}}}"
    if t == "concat":
        parts = ast_dict.get("parts", [])
        return "".join(unparse_formula_dict(p) for p in parts)
    return ""
