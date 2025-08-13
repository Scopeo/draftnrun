from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ada_backend.context import RequestContext, set_request_context


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that sets up RequestContext for every request.

    This middleware creates a new RequestContext with a unique request_id
    for every request. User authentication is handled separately by
    authenticated endpoints after JWT validation.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        context = RequestContext(request_id=uuid4())
        set_request_context(context)

        response = await call_next(request)
        return response
