import logging

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ada_backend.services.errors import ServiceError
from engine.components.errors import LLMProviderError
from engine.errors import EngineError

LOGGER = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI application."""

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        if exc.status_code >= 500:
            LOGGER.error("Service error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
        else:
            LOGGER.error("Service error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(LLMProviderError)
    async def llm_provider_error_handler(request: Request, exc: LLMProviderError) -> JSONResponse:
        LOGGER.warning(
            "LLM provider error on %s %s: %s",
            request.method,
            request.url.path,
            exc.provider_message,
        )
        return JSONResponse(status_code=exc.http_status, content={"detail": str(exc)})

    @app.exception_handler(EngineError)
    async def engine_error_handler(request: Request, exc: EngineError) -> JSONResponse:
        LOGGER.error("Engine error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(HTTPException)
    async def sentry_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if exc.__cause__ and exc.status_code >= 500:
            sentry_sdk.capture_exception(exc.__cause__)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred."})
