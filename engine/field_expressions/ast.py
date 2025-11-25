"""AST nodes for field expressions."""

from dataclasses import dataclass
from typing import List, Optional, Union


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

    parts: List[Union[LiteralNode, RefNode, "ExternalRefNode"]]


@dataclass(frozen=True)
class ExternalRefNode:
    """Reference to an external value (e.g. settings, secrets).

    Syntax: @{ $source.key }
    """

    source: str
    key: str


ExpressionNode = Union[LiteralNode, RefNode, ConcatNode, ExternalRefNode]
