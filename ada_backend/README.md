# ada_backend — Draft'n Run API Server

FastAPI backend for Draft'n Run: an AI workflow platform where users build, deploy, and monitor DAG-based pipelines of AI components.

## Architecture

```text
Router → Service → Repository (SQLAlchemy + PostgreSQL)
```

- **Routers** (`routers/`): FastAPI route handlers. ~33 files, ~163 endpoints. Auth via dependency injection.
- **Services** (`services/`): Business logic layer. Receives DB sessions from routers.
- **Repositories** (`repositories/`): SQLAlchemy CRUD operations.
- **Engine** (`../engine/`): Graph execution engine — runs DAGs of components.

### Service Map

| Process | Dockerfile | Port | Purpose |
|---|---|---|---|
| API server | `Dockerfile.api` | 8000 | FastAPI + Gunicorn, also runs the run queue worker thread |
| Scheduler | `Dockerfile.scheduler` | — | APScheduler cron jobs (separate process) |
| Ingestion worker | — (systemd) | — | Redis Stream consumer for data ingestion |
| Webhook worker | `Dockerfile.webhook-worker` | — | Redis Stream consumer for webhook events |
| MCP server | `mcp_server/Dockerfile` | 8090 | Standalone MCP interface (see `mcp_server/README.md`) |

## Authentication

Three mechanisms: **Supabase JWT** (dashboard users), **Scoped API keys** (project/org, `X-API-Key`), **Internal service keys** (`X-Ingestion-API-Key`, `X-Webhook-API-Key`, `X-Admin-API-Key`).

Four role tiers: `SUPER_ADMIN > ADMIN > DEVELOPER > MEMBER` (each includes all below).

Organization access is checked via Supabase Edge Functions (`check-org-access`, `check-super-admin`), **not local DB queries**.

See [docs/auth.md](docs/auth.md) for full details.

## API Surface

~163 endpoints across 25 domains. See [docs/api-reference.md](docs/api-reference.md) for the complete reference.

Key domains: Projects, Graphs (DAG editor), Runs, Agents, API Keys, Variables & Secrets, Knowledge Base, Ingestion, QA (datasets + LLM judges), Monitoring & Traces, Cron Jobs, Webhooks, Widgets, OAuth Connections, Credits.

## Graph Execution Engine

Workflows are directed acyclic graphs (DAGs) of components. The `GraphRunner` processes them via topological scheduling with `networkx`. Components implement the `Runnable` protocol with typed Pydantic I/O schemas.

Key concepts: **Ports** (typed I/O), **Port Mappings** (wiring between nodes), **Field Expressions** (JSON AST transforms), **ExecutionDirective** (control flow: continue/halt/selective routing), **Variable Resolution** (defaults → layered set overrides).

See [docs/engine.md](docs/engine.md) and [docs/payload-and-data-flow.md](docs/payload-and-data-flow.md).

## Environments

Each project has `draft` and `production` environments, bound to specific `GraphRunner` versions via `ProjectEnvironmentBinding`. Deployment flow: edit draft → `save-version` → `deploy` → `bind to env`.

## Workers

### Run Queue Worker

Embedded in the API process as a daemon thread. Uses Redis `BRPOPLPUSH` for reliable at-least-once delivery, per-worker heartbeat keys (60s TTL), and orphan recovery on startup.

### Webhook Worker

Separate process consuming from a Redis Stream (`REDIS_WEBHOOK_STREAM`). Forks subprocesses per event for isolation. See [docs/webhooks.md](docs/webhooks.md).

### Ingestion Worker

Separate process consuming from a Redis Stream (`REDIS_INGESTION_STREAM`). Handles document ingestion into the knowledge base.

## Database

PostgreSQL with multiple schemas:
- **`public`**: Core tables (projects, components, graphs, runs, API keys, secrets, webhooks, etc.)
- **`quality_assurance`**: QA datasets, entries, version outputs, judges, evaluations
- **`credits`**: Cost models, usage tracking, organization limits
- **`scheduler`**: Cron jobs, cron runs, polling history
- **`traces`**: Spans, span messages
- **`widget`**: Widget configurations

Migrations: Alembic (`make db-upgrade`). Seed data: `make db-seed`.

## External Integrations

- **Supabase**: Auth (JWT validation, Edge Functions), user/org data, file storage
- **LLM Providers**: OpenAI, Anthropic, Google, Mistral, Cerebras, Cohere (via completion service)
- **Qdrant**: Vector search for knowledge base
- **Nango**: OAuth proxy for third-party integrations (Slack, HubSpot, etc.)
- **Redis**: Run queue, webhook stream, ingestion stream, rate limiting, caching
- **S3/SeaweedFS**: File storage (documents, run results)
- **Sentry**: Error tracking and performance monitoring
- **OpenTelemetry + Prometheus**: Tracing and metrics

## Observability

- **Sentry**: `sentry-sdk` with FastAPI integration
- **OpenTelemetry**: Distributed tracing (Tempo exporter)
- **Prometheus**: Application metrics via `prometheus-fastapi-instrumentator`
- **Structured logging**: Python `logging` + `structlog`

## Commands

| Command | Description |
|---|---|
| `make run-draftnrun-agents-backend` | Run the API server |
| `make db-upgrade` | Apply Alembic migrations |
| `make db-seed` | Seed database with component catalog |
| `make trace-db-upgrade` | Apply trace schema migrations |
| `uv run python -m ada_backend.run_scheduler` | Run the cron scheduler |
| `uv run python -m ada_ingestion_system.worker.main` | Run the ingestion worker |
| `uv run pytest ada_backend` | Run tests |

## Domain Documentation

- [docs/auth.md](docs/auth.md) — authentication & authorization
- [docs/api-reference.md](docs/api-reference.md) — complete endpoint reference
- [docs/engine.md](docs/engine.md) — graph execution engine
- [docs/payload-and-data-flow.md](docs/payload-and-data-flow.md) — payload schema, field expressions, ctx propagation
- [docs/webhooks.md](docs/webhooks.md) — three webhook patterns
- [docs/qa-system.md](docs/qa-system.md) — datasets, judges, evaluations
- [docs/credits.md](docs/credits.md) — cost model, usage tracking
- [services/cron/Readme.md](services/cron/Readme.md) — cron system (registry, entrypoints)
