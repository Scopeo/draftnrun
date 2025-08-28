"""
Request context management for user authentication and permissions.

This module provides a thread-safe way to access user information throughout
the request lifecycle using Python's contextvars.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from ada_backend.schemas.auth_schema import SupabaseUser


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
