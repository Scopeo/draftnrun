"""
Execution context management for request lifecycle and scheduled jobs.

This module provides thread-safe access to contextual information via
Python's contextvars. Two context types are supported:

- RequestContext: set by HTTP middleware for every API request
- CronExecutionContext: set by the scheduler for every cron job run

Use get_execution_id() as a unified facade to get the current execution's
unique ID regardless of context type (useful for per-execution caching).
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from ada_backend.schemas.auth_schema import SupabaseUser

# ---------------------------------------------------------------------------
# Request context
# ---------------------------------------------------------------------------


@dataclass
class RequestContext:
    """
    Request-scoped context containing user authentication information.

    Every request gets a unique request_id for tracing. User authentication
    is optional and set when available.
    """

    request_id: UUID
    _user: Optional[SupabaseUser] = None

    def has_user(self) -> bool:
        """Check if user context is available."""
        return self._user is not None

    def set_user(self, user: SupabaseUser) -> None:
        """Set the user for the current request context."""
        self._user = user

    def require_user(self) -> SupabaseUser:
        """
        Get the user, raising an error if no user is authenticated.

        Returns:
            SupabaseUser: The authenticated user

        Raises:
            ValueError: If no user is authenticated
        """
        if not self._user:
            raise ValueError("Authentication required for this operation")
        return self._user


# Thread-safe context variable for storing request context
request_context: ContextVar[RequestContext] = ContextVar("request_context")


def set_request_context(context: RequestContext) -> None:
    """
    Set the request context.

    This should be called by middleware for every request to make request
    information available throughout the request lifecycle.

    Args:
        context: The RequestContext object to set
    """
    request_context.set(context)


def get_request_context() -> RequestContext:
    """
    Get the current request context.

    Returns:
        RequestContext: The current request context

    Raises:
        ValueError: If no context is available (endpoint didn't set context)
    """
    try:
        return request_context.get()
    except LookupError as exc:
        raise ValueError(
            "No request context available. This operation requires authentication.",
        ) from exc


# ---------------------------------------------------------------------------
# Cron execution context
# ---------------------------------------------------------------------------


@dataclass
class CronExecutionContext:
    """
    Context for a single cron job execution.

    Set by the scheduler before invoking any job logic. Add fields here as
    needed (org_id, project_id, etc.) without changing callers.
    """

    run_id: UUID
    cron_id: UUID


_cron_execution_context: ContextVar[CronExecutionContext] = ContextVar("cron_execution_context")


def set_cron_execution_context(context: CronExecutionContext) -> None:
    """Set the cron execution context for the current async task."""
    _cron_execution_context.set(context)


def get_cron_execution_context() -> CronExecutionContext:
    """
    Get the current cron execution context.

    Raises:
        ValueError: If called outside a cron job execution.
    """
    try:
        return _cron_execution_context.get()
    except LookupError as exc:
        raise ValueError("No cron execution context available.") from exc


# ---------------------------------------------------------------------------
# Unified execution ID facade
# ---------------------------------------------------------------------------


def get_execution_id() -> UUID:
    """
    Return a unique ID for the current unit of work, regardless of entry point.

    Resolution order:
      1. HTTP request  -> RequestContext.request_id
      2. Cron job      -> CronExecutionContext.run_id

    Raises:
        ValueError: If no execution context has been set.
    """
    try:
        return request_context.get().request_id
    except LookupError:
        pass
    try:
        return _cron_execution_context.get().run_id
    except LookupError:
        raise ValueError("No execution context available.")
