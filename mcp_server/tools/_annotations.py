"""Shared MCP tool annotation presets.

Annotations let MCP clients distinguish safe reads from destructive writes
(auto-approval, confirmation UX). Kept in a dependency-free module so both
the proxy factory and hand-written tools can import them without cycles.
"""

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
NON_DESTRUCTIVE_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
IDEMPOTENT_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
DESTRUCTIVE_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)
# Runs agents/workflows whose components may reach external systems (email, CRM, web).
EXECUTION = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
