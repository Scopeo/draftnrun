import logging
import threading
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import PrometheusFastApiInstrumentator
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from ada_backend.admin.admin import setup_admin
from ada_backend.graphql.schema import graphql_router
from ada_backend.instrumentation import setup_performance_instrumentation
from ada_backend.middleware.rate_limit_middleware import rate_limit_exceeded_handler
from ada_backend.middleware.request_context import RequestContextMiddleware
from ada_backend.routers.admin_tools_router import router as admin_tools_router
from ada_backend.routers.agent_router import router as agent_router
from ada_backend.routers.auth_router import router as auth_router
from ada_backend.routers.categories_router import router as categories_router
from ada_backend.routers.component_version_router import router as component_version_router
from ada_backend.routers.components_router import router as components_router
from ada_backend.routers.credits_router import router as credits_router
from ada_backend.routers.cron_router import router as cron_router
from ada_backend.routers.global_secret_router import router as global_secret_router
from ada_backend.routers.graph_router import router as graph_router
from ada_backend.routers.ingestion_database_router import router as ingestion_database_router
from ada_backend.routers.ingestion_task_router import router as ingestion_task_router
from ada_backend.routers.integration_router import router as integration_router
from ada_backend.routers.knowledge_router import router as knowledge_router
from ada_backend.routers.llm_judges_router import router as llm_judges_router
from ada_backend.routers.llm_models_router import router as llm_models_router
from ada_backend.routers.monitor_router import router as monitor_router
from ada_backend.routers.oauth_router import router as oauth_router
from ada_backend.routers.organization_qa_router import router as organization_qa_router
from ada_backend.routers.organization_router import router as org_router
from ada_backend.routers.project_router import router as project_router
from ada_backend.routers.qa_evaluation_router import router as qa_evaluation_router
from ada_backend.routers.qa_stream_router import router as qa_stream_router
from ada_backend.routers.quality_assurance_router import router as quality_assurance_router
from ada_backend.routers.run_router import router as run_router
from ada_backend.routers.run_stream_router import router as run_stream_router
from ada_backend.routers.s3_files_router import router as s3_files_router
from ada_backend.routers.source_router import router as source_router
from ada_backend.routers.template_router import router as template_router
from ada_backend.routers.trace_router import router as trace_router
from ada_backend.routers.variables_router import org_router as variables_router
from ada_backend.routers.webhooks.provider_webhooks_router import router as provider_webhooks_router
from ada_backend.routers.webhooks.webhook_internal_router import router as webhook_internal_router
from ada_backend.routers.webhooks.webhook_trigger_router import router as webhook_trigger_router
from ada_backend.routers.widget_router import router as widget_router
from ada_backend.services.rate_limit_service import limiter
from ada_backend.utils.redis_client import xgroup_create_if_not_exists
from ada_backend.workers.qa_queue_worker import _request_qa_drain, start_qa_queue_worker_thread
from ada_backend.workers.run_queue_worker import _request_drain, start_run_queue_worker_thread
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from logger import setup_logging
from settings import settings

setup_logging()

LOGGER = logging.getLogger(__name__)

set_trace_manager(tm=TraceManager(project_name="ada-backend"))

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        send_default_pii=settings.SENTRY_SEND_PII,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        enable_logs=True,
        profile_session_sample_rate=settings.SENTRY_PROFILE_SESSION_SAMPLE_RATE,
        profile_lifecycle="trace",
    )


def _join_worker(thread: threading.Thread | None, worker_name: str, item_name: str, timeout: float) -> None:
    if thread is None:
        return
    LOGGER.info("Waiting up to %ss for %s worker to finish current job...", timeout, worker_name)
    thread.join(timeout=timeout)
    if thread.is_alive():
        LOGGER.warning(
            "%s worker did not finish within %ss — in-flight %s will be recovered by the next pod on restart.",
            worker_name.capitalize(),
            timeout,
            item_name,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    - Ensures required Redis consumer groups exist.
    - Starts the run queue worker thread on startup and joins it on shutdown.
    """
    # Ensure Redis consumer groups exist before processing starts
    xgroup_create_if_not_exists(settings.REDIS_INGESTION_STREAM, settings.REDIS_CONSUMER_GROUP)
    xgroup_create_if_not_exists(settings.REDIS_WEBHOOK_STREAM, settings.REDIS_CONSUMER_GROUP)

    # Start queue worker threads and set up graceful shutdown
    worker_thread = start_run_queue_worker_thread()
    qa_worker_thread = start_qa_queue_worker_thread()

    try:
        yield
    finally:
        _request_drain()
        _request_qa_drain()
        timeout = settings.WORKER_SHUTDOWN_TIMEOUT_SECONDS
        _join_worker(worker_thread, "run queue", "run", timeout)
        _join_worker(qa_worker_thread, "QA queue", "QA session", timeout)


app = FastAPI(
    title="Ada Backend",
    lifespan=lifespan,
    description="API for managing and running LLM agents",
    version="0.1.0",
    openapi_tags=[
        {
            "name": "Auth",
            "description": "Authentication operations. API key generation.",
        },
        {
            "name": "Organization",
            "description": "Operations with organizations, including "
            "adding secrets and managing organization settings",
        },
        {
            "name": "GraphQL",
            "description": "GraphQL operations for querying and mutating data",
        },
        {
            "name": "Projects",
            "description": "Operations with projects, including creation, "
            "deletion, and management of project settings",
        },
        {
            "name": "Workflows",
            "description": "Provides endpoints for managing workflow projects",
        },
        {
            "name": "Agents",
            "description": "Provides endpoints for managing agent projects",
        },
        {
            "name": "Integrations",
            "description": "Endpoints for managing integrations with external services",
        },
        {
            "name": "Templates",
            "description": "Endpoints for managing templates, including "
            "retrieving production templates and creating new templates",
        },
        {
            "name": "Graph",
            "description": "Operations with graph runner within projects, "
            "including updating and retrieving graph runner configurations",
        },
        {
            "name": "Metrics",
            "description": "Endpoints for retrieving metrics",
        },
        {
            "name": "Components",
            "description": "Endpoints for managing components",
        },
        {
            "name": "Categories",
            "description": "Endpoints for managing categories",
        },
        {
            "name": "Sources",
            "description": "Endpoints for managing organization sources, such as vectorstores",
        },
        {
            "name": "Ingestion Task",
            "description": "Endpoints for managing ingestion tasks for organization sources",
        },
        {
            "name": "Cron Jobs",
            "description": "Endpoints for managing scheduled cron jobs for organizations",
        },
        {
            "name": "Quality Assurance",
            "description": "Endpoints for managing quality assurance datasets, versions and inputs per project",
        },
        {
            "name": "QA Evaluation",
            "description": "Endpoints for managing LLM judges and evaluations for quality assurance",
        },
        {
            "name": "Ingestion Database",
            "description": "Endpoints for managing ingestion database for organization sources",
        },
        {
            "name": "LLM Models",
            "description": "Endpoints for managing LLM models",
        },
        {
            "name": "Knowledge",
            "description": "Endpoints for exploring knowledge files and chunks",
        },
        {
            "name": "Credits",
            "description": "Endpoints for managing credits",
        },
        {
            "name": "Widget",
            "description": "Endpoints for embeddable chat widgets",
        },
        {
            "name": "Webhooks",
            "description": "Endpoints for receiving webhook events from external providers",
        },
    ],
)

PrometheusFastApiInstrumentator().instrument(app).expose(app, endpoint="/metrics")

# Exempt /metrics from rate limiting (route is auto-generated, can't use decorator)
for route in app.routes:
    if getattr(route, "path", None) == "/metrics":
        limiter.exempt(route.endpoint)
        break

# Setup HTTP metrics and traces instrumentation
if settings.ENABLE_OBSERVABILITY_STACK:
    setup_performance_instrumentation(app)

setup_admin(app)

app.include_router(auth_router)
app.include_router(org_router)
app.include_router(project_router)
app.include_router(run_router)
app.include_router(run_stream_router)
app.include_router(variables_router)
app.include_router(agent_router)
app.include_router(integration_router)
app.include_router(oauth_router)
app.include_router(template_router)
app.include_router(source_router)
app.include_router(ingestion_task_router)
app.include_router(s3_files_router)
app.include_router(components_router)
app.include_router(component_version_router)
app.include_router(categories_router)
app.include_router(graph_router)
app.include_router(organization_qa_router)
app.include_router(quality_assurance_router)
app.include_router(qa_stream_router)
app.include_router(llm_judges_router)
app.include_router(qa_evaluation_router)
app.include_router(graphql_router, prefix="/graphql")
app.include_router(trace_router)
app.include_router(admin_tools_router)
app.include_router(cron_router)
app.include_router(global_secret_router)
app.include_router(knowledge_router)
app.include_router(ingestion_database_router)
app.include_router(llm_models_router)
app.include_router(monitor_router)
app.include_router(credits_router)
app.include_router(widget_router)
app.include_router(provider_webhooks_router)
app.include_router(webhook_internal_router)
app.include_router(webhook_trigger_router)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


@app.exception_handler(HTTPException)
async def sentry_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if exc.__cause__ and exc.status_code >= 500:
        sentry_sdk.capture_exception(exc.__cause__)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@limiter.exempt
def read_root():
    return {"message": "Welcome to the LLM Agent Admin Interface!"}


@app.get("/health")
@limiter.exempt
def health_check():
    return JSONResponse(content={"status": "ok"}, status_code=200)


if __name__ == "__main__":
    import uvicorn

    # Feature metrics endpoint (prometheus_metric.py)
    start_http_server(port=9100, addr="0.0.0.0")

    uvicorn.run(
        "ada_backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.RELOAD_SCOPEO_AGENTS_BACKEND,
    )
