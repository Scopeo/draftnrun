"""
Parameter Interpolation System for Graph Runner

This module provides template string parsing and resolution for component parameters.
Users can embed references to other component outputs using {{@nodeId.portName}} syntax.

Examples:
    - "{{@agent1.response}}" -> Direct reference to agent1's response output
    - "Hello {{@agent1.name}}, welcome!" -> Mixed constant text and reference
    - "Result: {{@calc.value}} (status: {{@calc.status}})" -> Multiple references
    - "Use \\{\\{ for literal braces" -> Escaped braces become {{

The system maintains backward compatibility with port mappings while providing
a more user-friendly way to wire data between components.
"""

import logging
import re
from typing import Any, Union
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)


@dataclass
class TextSegment:
    """A plain text segment in a template."""

    type: str = "text"  # Always "text"
    value: str = ""  # The text content


@dataclass
class ReferenceSegment:
    """A reference to another component's output."""

    type: str = "reference"  # Always "reference"
    node_id: str = ""  # The source component instance ID
    port_name: str = ""  # The output port name


# Type alias for segments
Segment = Union[TextSegment, ReferenceSegment]


class ParameterInterpolator:
    """
    Parses and resolves template strings with embedded component output references.

    Template Syntax:
        {{@nodeId.portName}} - Reference to a component output
        \\{\\{ - Escaped braces (rendered as {{)

    The interpolator handles:
    - Parsing templates into segments (text and references)
    - Extracting dependencies for execution ordering
    - Resolving templates with actual runtime values
    - Type coercion when mixing constants and references
    """

    # Template syntax constants
    TEMPLATE_PREFIX = "{{@"
    TEMPLATE_SUFFIX = "}}"
    TEMPLATE_SEPARATOR = "."
    ESCAPED_BRACE = "{{"

    # Regex pattern to match {{@nodeId.portName}} references
    # Allows for: {{@node-id_123.port_name-2}}
    REFERENCE_PATTERN = re.compile(r"\{\{@([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_-]+)\}\}")

    # Pattern for escaped braces
    ESCAPED_BRACE_PATTERN = re.compile(r"\\{\\{")

    @classmethod
    def is_template(cls, value: Any) -> bool:
        """
        Check if a value contains template references.

        Args:
            value: The value to check (typically a string)

        Returns:
            True if value contains {{@...}} references
        """
        if not isinstance(value, str):
            return False
        return bool(cls.REFERENCE_PATTERN.search(value))

    @classmethod
    def parse_template(cls, template: str) -> list[Segment]:
        """
        Parse a template string into segments of text and references.

        Args:
            template: Template string with optional {{@nodeId.portName}} references

        Returns:
            List of TextSegment and ReferenceSegment objects

        Example:
            >>> parse_template("Hello {{@agent1.name}}!")
            [TextSegment(value="Hello "),
             ReferenceSegment(node_id="agent1", port_name="name"),
             TextSegment(value="!")]
        """
        segments: list[Segment] = []
        last_end = 0

        # Find all references in the template
        for match in cls.REFERENCE_PATTERN.finditer(template):
            # Add text before this reference
            if match.start() > last_end:
                text = template[last_end : match.start()]
                # Unescape any escaped braces
                text = cls.ESCAPED_BRACE_PATTERN.sub(cls.ESCAPED_BRACE, text)
                segments.append(TextSegment(type="text", value=text))

            # Add the reference
            node_id = match.group(1)
            port_name = match.group(2)
            segments.append(ReferenceSegment(type="reference", node_id=node_id, port_name=port_name))

            last_end = match.end()

        # Add any remaining text after the last reference
        if last_end < len(template):
            text = template[last_end:]
            # Unescape any escaped braces
            text = cls.ESCAPED_BRACE_PATTERN.sub(cls.ESCAPED_BRACE, text)
            segments.append(TextSegment(type="text", value=text))

        return segments

    @classmethod
    def extract_references(cls, template: str) -> list[tuple[str, str]]:
        """
        Extract all component output references from a template.

        Args:
            template: Template string to analyze

        Returns:
            List of (node_id, port_name) tuples

        Example:
            >>> extract_references("{{@a.x}} and {{@b.y}}")
            [("a", "x"), ("b", "y")]
        """
        references = []
        for match in cls.REFERENCE_PATTERN.finditer(template):
            node_id = match.group(1)
            port_name = match.group(2)
            references.append((node_id, port_name))
        return references

    @classmethod
    def resolve_template(cls, template: str, resolved_outputs: dict[str, dict[str, Any]]) -> Any:
        """
        Resolve a template by replacing references with actual values.

        Args:
            template: Template string with {{@nodeId.portName}} references
            resolved_outputs: Dict mapping node_id -> {port_name: value}

        Returns:
            Resolved value. Returns original type if single reference,
            otherwise returns string with all references replaced.

        Raises:
            ValueError: If a referenced output is not found

        Example:
            >>> outputs = {"agent1": {"name": "Alice"}}
            >>> resolve_template("Hello {{@agent1.name}}!", outputs)
            "Hello Alice!"

            >>> resolve_template("{{@agent1.name}}", outputs)
            "Alice"  # Direct value, not stringified
        """
        if not isinstance(template, str):
            # Not a template, return as-is
            return template

        if not cls.is_template(template):
            # No references, return as-is (could still have escaped braces)
            return cls.ESCAPED_BRACE_PATTERN.sub(cls.ESCAPED_BRACE, template)

        segments = cls.parse_template(template)

        # Optimization: If template is a single reference with no text, return the value directly
        # This preserves the original type (dict, list, etc.) instead of stringifying
        if len(segments) == 1 and isinstance(segments[0], ReferenceSegment):
            ref = segments[0]
            value = cls._resolve_reference(ref, resolved_outputs)
            return value

        # Multiple segments or mixed text+reference: stringify everything
        result_parts = []
        for segment in segments:
            if isinstance(segment, TextSegment):
                result_parts.append(segment.value)
            elif isinstance(segment, ReferenceSegment):
                value = cls._resolve_reference(segment, resolved_outputs)
                # Convert to string for concatenation
                result_parts.append(cls._value_to_string(value))

        return "".join(result_parts)

    @classmethod
    def _resolve_reference(cls, ref: ReferenceSegment, resolved_outputs: dict[str, dict[str, Any]]) -> Any:
        """
        Resolve a single reference to its actual value.

        Args:
            ref: The reference segment to resolve
            resolved_outputs: Available outputs from previous components

        Returns:
            The referenced value

        Raises:
            ValueError: If the reference cannot be resolved
        """
        node_outputs = resolved_outputs.get(ref.node_id)
        if node_outputs is None:
            raise ValueError(
                f"Cannot resolve reference {{{{@{ref.node_id}.{ref.port_name}}}}}: "
                f"Component '{ref.node_id}' not found or has not been executed yet"
            )

        if ref.port_name not in node_outputs:
            available_ports = ", ".join(node_outputs.keys())
            raise ValueError(
                f"Cannot resolve reference {{{{@{ref.node_id}.{ref.port_name}}}}}: "
                f"Port '{ref.port_name}' not found in component '{ref.node_id}'. "
                f"Available ports: {available_ports}"
            )

        return node_outputs[ref.port_name]

    @classmethod
    def _value_to_string(cls, value: Any) -> str:
        """
        Convert any value to string for template concatenation.

        Handles special cases:
        - None -> empty string
        - Lists/dicts -> JSON representation
        - Other types -> str()
        """
        if value is None:
            return ""
        elif isinstance(value, (list, dict)):
            import json

            return json.dumps(value, ensure_ascii=False)
        else:
            return str(value)
