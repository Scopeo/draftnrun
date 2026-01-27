"""AST nodes for field expressions."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Union


@dataclass(frozen=True)
class LiteralNode:
    """Literal value node."""

    value: str


@dataclass(frozen=True)
class RefNode:
    """Reference to another component's output.

    Optionally supports extracting a key from dict outputs using `::key` syntax.
    """

    instance: str
    port: str
    key: Optional[str] = None


@dataclass(frozen=True)
class ConcatNode:
    """Concatenation of literal and ref parts."""

    parts: List[Union[LiteralNode, RefNode]]


@dataclass(frozen=True)
class JsonBuildNode:
    """Build JSON structure with refs that preserve object types.

    Template can contain special placeholder strings that will be replaced
    with evaluated ref values (preserving their Python types, not stringified).

    Example:
        template: [{"value_a": "__REF_0__", "operator": "is_not_empty"}]
        refs: {"__REF_0__": RefNode(instance="abc", port="messages")}

    This allows building JSON structures with component outputs while
    preserving their types (lists stay lists, dicts stay dicts, etc.)
    """

    template: Union[dict, list]  # Template structure with placeholders
    refs: Dict[str, RefNode]  # Placeholder string -> RefNode mapping


ExpressionNode = Union[LiteralNode, RefNode, ConcatNode, JsonBuildNode]
