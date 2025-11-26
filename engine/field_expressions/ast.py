"""AST nodes for field expressions."""

from dataclasses import dataclass
from enum import StrEnum
from typing import List, Optional, Union


class VarType(StrEnum):
    """Types of injectable variables."""

    SECRETS = "secrets"
    # Future: SETTINGS = "settings", ENV = "env"


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

    parts: List[Union[LiteralNode, RefNode, "VarNode"]]


@dataclass(frozen=True)
class VarNode:
    """Reference to an injected variable (e.g. secrets, settings).

    Syntax: @{ $var_type.id }
    Example: @{ $secrets.550e8400-e29b-41d4-a716-446655440000 }
    """

    var_type: VarType
    key: str  # UUID of the entity (e.g. OrganizationSecret.id)


ExpressionNode = Union[LiteralNode, RefNode, ConcatNode, VarNode]
