"""AST nodes for field expressions."""

from dataclasses import dataclass
from typing import List, Union


@dataclass(frozen=True)
class LiteralNode:
    """Literal value node."""

    value: str


@dataclass(frozen=True)
class RefNode:
    """Reference to another component's output."""

    instance: str
    port: str


@dataclass(frozen=True)
class ConcatNode:
    """Concatenation of literal and ref parts."""

    parts: List[Union[LiteralNode, RefNode]]


ExpressionNode = Union[LiteralNode, RefNode, ConcatNode]
