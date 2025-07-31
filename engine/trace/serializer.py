import json
from typing import Any, Optional

from engine.agent.utils import shorten_base64_string


# TODO : when observability will handle json display, change the default indent to 0
def serialize_to_json(obj: Any, indent: int = 2, shorten_string: bool = False) -> str:
    """
    Recursively serialize an object to JSON string.
    Handles nested objects, lists, sets, Pydantic models, and primitive types.
    Protects against circular references.

    Args:
        obj: The object to serialize
        indent: JSON indentation level

    Returns:
        JSON string representation of the object
    """
    serialized_obj = _serialize_object(obj, shorten_string=shorten_string)
    return json.dumps(serialized_obj, indent=indent)


def _serialize_object(obj: Any, visited: Optional[set] = None, shorten_string: bool = False) -> Any:
    """
    Recursively serialize an object to make it JSON-compatible.
    Handles nested objects, lists, sets, Pydantic models, and primitive types.
    Protects against circular references.

    Args:
        obj: The object to serialize
        visited: Set of visited object IDs to prevent circular references

    Returns:
        JSON-serializable representation of the object
    """
    if visited is None:
        visited = set()

    if obj is None:
        return None
    elif isinstance(obj, str):
        if shorten_string:
            return shorten_base64_string(obj)
        else:
            return obj
    elif isinstance(obj, (int, float, bool)):
        return obj
    elif isinstance(obj, (list, tuple, set)):
        return [_serialize_object(item, visited, shorten_string) for item in obj]
    elif isinstance(obj, dict):
        # Check for circular references
        obj_id = id(obj)
        if obj_id in visited:
            return f"<Circular reference to {type(obj).__name__}>"
        visited.add(obj_id)
        return {k: _serialize_object(v, visited, shorten_string) for k, v in obj.items()}
    elif hasattr(obj, "model_dump"):
        # Handle Pydantic BaseModel objects
        try:
            return _serialize_object(obj.model_dump(), visited, shorten_string)
        except Exception:
            return f"<{type(obj).__name__} object>"
    else:
        # For any other type, try to convert to string
        try:
            return str(obj)
        except Exception:
            return f"<{type(obj).__name__} object>"
