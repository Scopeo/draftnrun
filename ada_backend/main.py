from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import PrometheusFastApiInstrumentator

from ada_backend.admin.admin import setup_admin
from ada_backend.instrumentation import setup_performance_instrumentation
from ada_backend.middleware.request_context import RequestContextMiddleware
from ada_backend.routers.categories_router import router as categories_router
from ada_backend.routers.project_router import router as project_router
from ada_backend.routers.template_router import router as template_router
from ada_backend.routers.integration_router import router as integration_router
from ada_backend.routers.global_secret_router import router as global_secret_router
from ada_backend.routers.auth_router import router as auth_router
from ada_backend.routers.source_router import router as source_router
from ada_backend.routers.ingestion_task_router import router as ingestion_task_router
from ada_backend.routers.components_router import router as components_router
from ada_backend.routers.component_version_router import router as component_version_router
from ada_backend.routers.graph_router import router as graph_router
from ada_backend.routers.s3_files_router import router as s3_files_router
from ada_backend.routers.quality_assurance_router import router as quality_assurance_router
from ada_backend.routers.llm_judges_router import router as llm_judges_router
from ada_backend.routers.qa_evaluation_router import router as qa_evaluation_router
from ada_backend.graphql.schema import graphql_router
from ada_backend.routers.organization_router import router as org_router
from ada_backend.routers.trace_router import router as trace_router
from ada_backend.routers.admin_tools_router import router as admin_tools_router
from ada_backend.routers.cron_router import router as cron_router
from ada_backend.routers.agent_router import router as agent_router
from ada_backend.routers.knowledge_router import router as knowledge_router
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from settings import settings
from logger import setup_logging
from ada_backend.routers.ingestion_database_router import router as ingestion_database_router
from ada_backend.routers.llm_models_router import router as llm_models_router
from ada_backend.routers.credits_router import router as credits_router

setup_logging()

set_trace_manager(tm=TraceManager(project_name="ada-backend"))

app = FastAPI(
    title="Ada Backend",
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
    ],
)

PrometheusFastApiInstrumentator().instrument(app).expose(app, endpoint="/metrics")

# Setup HTTP metrics and traces instrumentation
if settings.ENABLE_OBSERVABILITY_STACK:
    setup_performance_instrumentation(app)

setup_admin(app)

app.include_router(auth_router)
app.include_router(org_router)
app.include_router(project_router)
app.include_router(agent_router)
app.include_router(integration_router)
app.include_router(template_router)
app.include_router(source_router)
app.include_router(ingestion_task_router)
app.include_router(s3_files_router)
app.include_router(components_router)
app.include_router(component_version_router)
app.include_router(categories_router)
app.include_router(graph_router)
app.include_router(quality_assurance_router)
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
app.include_router(credits_router)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Welcome to the LLM Agent Admin Interface!"}


@app.get("/health")
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
