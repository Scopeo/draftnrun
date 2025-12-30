"""
Simplified type coercion system for multi-port I/O refactor.

This module provides a streamlined coercion system that handles essential
type conversions between components in the workflow automation platform.

The system is designed to be simple and intuitive - just register coercers
for the type pairs you need, and the system handles the rest.
"""

import logging
from typing import Any, Type, Callable, Optional, Union, get_origin, get_args

from engine.agent.types import ChatMessage, AgentPayload, SourceChunk

LOGGER = logging.getLogger(__name__)

GRAPH_RUNTIME_TARGET_TYPES: frozenset[type] = frozenset(
    {
        str,
        int,
        float,
        bool,
        dict,
        list[str],
        list[dict],
        list[ChatMessage],
        ChatMessage,
        AgentPayload,
        SourceChunk,
    }
)


# ============================================================================
# CORE COERCION FUNCTIONS
# ============================================================================


def extract_string_from_messages(messages: list[ChatMessage]) -> str:
    """Extract string from list of ChatMessage objects."""
    if not messages:
        return ""
    return messages[-1].to_string()


def extract_string_from_dict_list(messages: list[dict]) -> str:
    """Extract string from list of message dicts (legacy format)."""
    if not messages:
        return ""
    # Get last message content
    last_message = messages[-1]
    content = last_message.get("content", "")
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        return " ".join(str(item) for item in content if item)
    elif content == "":
        return ""
    else:
        # For non-string, non-list content, raise an error
        raise CoercionError(
            type(content),
            str,
            content,
            f"Expected string or list in dict content, got {type(content).__name__}",
        )


def convert_dict_list_to_chatmessage_list(messages: list[dict]) -> list[ChatMessage]:
    """Convert list of dict messages to list of ChatMessage objects."""
    return [ChatMessage(**msg) for msg in messages]


def extract_string_from_dict(data: dict) -> str:
    """Extract string from dict with various legacy formats."""
    # ChatMessage-like structure
    if "content" in data and isinstance(data["content"], str):
        return data["content"]

    # AgentPayload-like structure with messages
    if "messages" in data and isinstance(data["messages"], list) and data["messages"]:
        # Handle ChatMessage objects
        if isinstance(data["messages"][0], ChatMessage):
            return data["messages"][-1].to_string()
        else:
            return extract_string_from_dict_list(data["messages"])

    # Common output fields
    for field in ["output", "response", "result", "text", "message"]:
        if field in data and isinstance(data[field], str):
            return data[field]

    # Nested content
    if "data" in data and isinstance(data["data"], dict):
        return extract_string_from_dict(data["data"])

    # Fallback to string conversion
    return str(data)


class CoercionError(Exception):
    """Raised when a coercion operation fails."""

    def __init__(self, source_type: Type, target_type: Type, value: Any, reason: str = ""):
        self.source_type = source_type
        self.target_type = target_type
        self.value = value
        self.reason = reason
        source_name = source_type.__name__ if hasattr(source_type, "__name__") else str(source_type)
        target_name = target_type.__name__ if hasattr(target_type, "__name__") else str(target_type)
        super().__init__(f"Cannot coerce {source_name} to {target_name}: {reason}")


class CoercionMatrix:
    """
    Simple and intuitive coercion system.

    This class provides a straightforward coercion strategy:
    1. Already correct type - pass through
    2. Direct coercion - use registered coercers
    3. Primitive fallback - convert to basic types
    4. Fail with clear error

    The system is designed to be easy to understand and extend.
    """

    def __init__(self):
        self._coercers: dict[tuple[Type, Type], Callable[[Any], Any]] = {}
        self._fallbacks: dict[Type, Callable[[Any], Any]] = {}
        self._register_essential_coercers()
        self._register_primitive_fallbacks()

    def _register_essential_coercers(self):
        """Register essential coercers for the system to work."""

        # String extraction from complex types
        self._coercers[(list[ChatMessage], str)] = extract_string_from_messages
        self._coercers[(ChatMessage, str)] = lambda x: x.to_string()
        self._coercers[(SourceChunk, str)] = lambda x: x.to_string()
        self._coercers[(AgentPayload, str)] = lambda x: x.to_string()
        self._coercers[(dict, str)] = extract_string_from_dict
        self._coercers[(list[dict], str)] = extract_string_from_dict_list
        self._coercers[(list[dict], list[ChatMessage])] = convert_dict_list_to_chatmessage_list
        self._coercers[(type(None), str)] = lambda x: ""

        # Passthrough coercions (no-op)
        self._coercers[(list[ChatMessage], list[ChatMessage])] = lambda x: x
        self._coercers[(dict, dict)] = lambda x: x
        self._coercers[(str, Optional[str])] = lambda x: x
        self._coercers[(dict, Optional[dict])] = lambda x: x

        # Cross-type conversions
        self._coercers[(list[ChatMessage], AgentPayload)] = lambda x: AgentPayload(messages=x)
        self._coercers[(AgentPayload, list[ChatMessage])] = lambda x: x.messages
        self._coercers[(AgentPayload, dict)] = lambda x: x.model_dump()
        self._coercers[(dict, AgentPayload)] = lambda x: (
            AgentPayload(**x) if "messages" in x else AgentPayload(messages=[])
        )
        self._coercers[(list[ChatMessage], dict)] = lambda x: {"messages": x}

        # List conversions
        self._coercers[(str, list[str])] = lambda x: [x]
        self._coercers[(str, Optional[list[str]])] = lambda x: [x]
        self._coercers[(int, list[str])] = lambda x: [str(x)]
        self._coercers[(float, list[str])] = lambda x: [str(x)]

        # Message conversions
        self._coercers[(dict, list[ChatMessage])] = lambda x: x.get("messages", [])
        self._coercers[(str, list[ChatMessage])] = lambda x: [ChatMessage(role="user", content=x)]
        self._coercers[(dict, ChatMessage)] = lambda x: (
            ChatMessage(**x) if "role" in x else ChatMessage(role="user", content=str(x))
        )

        # Generic fallbacks
        self._coercers[(list, str)] = lambda x: str(x)
        self._coercers[(type(Any), str)] = lambda x: str(x)
        self._coercers[(Any, str)] = lambda x: str(x)

        LOGGER.debug(f"Registered {len(self._coercers)} essential coercers")

    def _register_primitive_fallbacks(self):
        """Register fallbacks for primitive type conversions."""
        self._fallbacks[str] = lambda x: "" if x is None else str(x)
        self._fallbacks[int] = lambda x: int(x)
        self._fallbacks[float] = lambda x: float(x)
        self._fallbacks[bool] = lambda x: bool(x)

        LOGGER.debug(f"Registered {len(self._fallbacks)} primitive fallbacks")

    def register_coercer(self, source_type: Type, target_type: Type, coercer: Callable[[Any], Any]):
        """Register a custom coercer for a specific type pair."""
        self._coercers[(source_type, target_type)] = coercer
        LOGGER.debug(f"Registered coercer: {source_type.__name__} -> {target_type.__name__}")

    def register_fallback(self, target_type: Type, fallback: Callable[[Any], Any]):
        """Register a fallback coercer for a target type."""
        self._fallbacks[target_type] = fallback
        LOGGER.debug(f"Registered fallback: {target_type.__name__}")

    def coerce(self, value: Any, target_type: Type | str, source_type: Optional[Type | str] = None) -> Any:
        if source_type is None:
            source_type = self._get_type_key(value)

        # Convert string type representations to actual types
        target_type = self._resolve_type(target_type)
        source_type = self._resolve_type(source_type)

        # Normalize parameterized dict types (e.g., dict[str, Any] -> dict)
        target_type = self._normalize_dict_type(target_type)
        source_type = self._normalize_dict_type(source_type)

        # Handle typing.Any - always pass through (delete after migration)
        if target_type == type(Any) or str(target_type) == "typing.Any":
            return value

        # 1. Check if already correct type
        if self._is_already_correct_type(value, target_type):
            return value

        # 2. Handle Optional types by coercing to inner type
        if self._is_optional_type(target_type):
            inner_type = self._get_optional_inner_type(target_type)
            return self.coerce(value, inner_type, source_type)

        # 3. Try direct coercion
        coercer = self._coercers.get((source_type, target_type))
        if coercer:
            try:
                return coercer(value)
            except Exception as e:
                LOGGER.debug(f"Direct coercion failed: {e}")
                raise CoercionError(source_type, target_type, value, str(e)) from e

        # 4. Try fallback coercion (for primitive types)
        fallback_coercer = self._fallbacks.get(target_type)
        if fallback_coercer:
            try:
                return fallback_coercer(value)
            except Exception as e:
                LOGGER.debug(f"Fallback coercion failed: {e}")
                raise CoercionError(source_type, target_type, value, str(e)) from e

        # 5. Fail-Open: If no explicit coercion is found, return the value for downstream validation.
        # This lets unhandled types (enums, dates, etc.) pass through for later checks.
        LOGGER.debug(
            f"No coercion path from {source_type.__name__} to {target_type.__name__}. "
            "Returning value as-is for downstream validation."
        )
        return value

    def can_coerce(self, source_type: Type | str, target_type: Type | str) -> bool:
        """Check if a coercion path exists between two types."""
        # Convert string type representations to actual types
        target_type = self._resolve_type(target_type)
        source_type = self._resolve_type(source_type)

        # Normalize parameterized dict types
        target_type = self._normalize_dict_type(target_type)
        source_type = self._normalize_dict_type(source_type)

        # Handle typing.Any - always can coerce (delete after migration)
        if target_type == type(Any) or str(target_type) == "typing.Any":
            return True

        # Check if already correct type
        if source_type == target_type:
            return True

        # Check for direct coercer
        if (source_type, target_type) in self._coercers:
            return True

        # Check for Optional type handling
        if self._is_optional_type(target_type):
            inner_type = self._get_optional_inner_type(target_type)
            return self.can_coerce(source_type, inner_type)

        # Check for fallback coercer
        if target_type in self._fallbacks:
            return True

        # Non graph-runtime types defer to schema validation
        if not self.should_attempt_coercion(target_type):
            return True

        return False

    def _is_optional_type(self, target_type: Type) -> bool:
        """Check if a type is Optional[SomeType]."""
        origin = get_origin(target_type)
        if origin is Union:
            args = get_args(target_type)
            return len(args) == 2 and type(None) in args
        return False

    def _get_optional_inner_type(self, target_type: Type) -> Type:
        """Get the inner type from Optional[InnerType]."""
        args = get_args(target_type)
        return args[0] if args[0] is not type(None) else args[1]

    def _is_already_correct_type(self, value: Any, target_type: Type) -> bool:
        """Check if value is already of the correct type, handling parameterized generics."""
        try:
            if target_type == list[ChatMessage]:
                return isinstance(value, list) and all(isinstance(item, ChatMessage) for item in value)
            elif target_type == list[str]:
                return isinstance(value, list) and all(isinstance(item, str) for item in value)
            elif target_type == list[dict]:
                return isinstance(value, list) and all(isinstance(item, dict) for item in value)
            else:
                return isinstance(value, target_type)
        except TypeError:
            # Handle parameterized generics that can't be used with isinstance
            return False

    def _get_type_key(self, value: Any) -> Type | str:
        """Get the type key for a value, handling special cases like list[ChatMessage]."""
        if isinstance(value, list):
            if not value:
                return list
            elif all(isinstance(item, ChatMessage) for item in value):
                return list[ChatMessage]
            elif all(isinstance(item, dict) for item in value):
                return list[dict]
            else:
                return list
        elif isinstance(value, dict):
            return dict
        else:
            return type(value)

    def _normalize_dict_type(self, type_hint: Type) -> Type:
        """Normalize parameterized dict types (e.g., dict[str, Any]) to plain dict."""
        origin = get_origin(type_hint)
        if origin is dict:
            # Parameterized dict (e.g., dict[str, Any]) -> plain dict
            return dict
        return type_hint

    def _resolve_type(self, type_hint: Type | str) -> Type:
        """Convert string type representations to actual types."""
        if isinstance(type_hint, str):
            if type_hint == "list[ChatMessage]":
                return list[ChatMessage]
            elif type_hint == "list[str]":
                return list[str]
            elif type_hint == "list[dict]":
                return list[dict]
            else:
                # For other string types, try to evaluate them
                # This is a fallback for any other string representations
                return str  # Default fallback
        return type_hint

    def should_attempt_coercion(self, target_type: Type | str) -> bool:
        """Return True when the matrix should try to coerce to ``target_type``."""
        normalized_type = self._resolve_type(target_type)
        normalized_type = self._normalize_dict_type(normalized_type)

        origin = get_origin(normalized_type)
        if origin is list:  # typing.List[T] -> list[T]
            args = get_args(normalized_type)
            inner_type = args[0] if args else Any
            normalized_type = list[self._resolve_type(inner_type)]
        elif origin is dict:  # typing.Dict[K, V] -> dict
            normalized_type = dict

        if normalized_type == type(Any) or str(normalized_type) == "typing.Any":
            return False

        if self._is_optional_type(normalized_type):
            inner_type = self._get_optional_inner_type(normalized_type)
            return self.should_attempt_coercion(inner_type)

        return normalized_type in GRAPH_RUNTIME_TARGET_TYPES


def create_default_coercion_matrix() -> CoercionMatrix:
    """Create a new coercion matrix with default coercers registered."""
    return CoercionMatrix()


# Global coercion matrix instance for backward compatibility
_default_coercion_matrix = create_default_coercion_matrix()


def get_coercion_matrix() -> CoercionMatrix:
    """Get the default global coercion matrix instance."""
    return _default_coercion_matrix


def coerce_value(value: Any, target_type: Type | str, source_type: Optional[Type | str] = None) -> Any:
    """Convenience function to coerce a value using the default coercion matrix."""
    return _default_coercion_matrix.coerce(value, target_type, source_type)
