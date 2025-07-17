# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the backend for Draft'n Run, an AI platform that provides agent management and execution capabilities. The system is built with FastAPI and uses a modular architecture with three main layers:

1. **ada_backend**: FastAPI-based backend with repository-service-controller architecture
2. **engine**: Core agent execution engine with graph-based workflows
3. **data_ingestion**: Document processing and ingestion system

## Essential Development Commands

### Running the Application
```bash
# Start the main backend server
make run-draftnrun-agents-backend

# Start backend in production mode
make run-backend-prod

# Start the ingestion worker
uv run python -m ada_ingestion_system.worker.main
```

### Database Management
```bash
# Apply database migrations
make db-upgrade

# Create new migration
make db-revision message="description"

# Seed database with test data
make db-seed

# Reset database (development only)
make db-reset

# Trace database migrations
make trace-db-upgrade
make trace-db-revision message="description"
```

### Testing and Quality
```bash
# Run tests with coverage
make test

# Format code with Black
make format

# Run quality checks (flake8 + black)
make quality-check

# Run full pre-push checks
make pre-push
```

### Service Management
```bash
# Start all services (postgres, redis, qdrant, prometheus, seaweedfs)
cd services && docker compose up -d

# Stop all services
cd services && docker compose down -v

# Start Supabase services
supabase start
supabase functions serve
```

## Architecture Overview

### Core Components

**ada_backend/**: FastAPI backend with clean architecture
- `models.py`: Database schemas (Components, Projects, Organizations, etc.)
- `repositories/`: Database CRUD operations
- `services/`: Business logic and component instantiation
- `routers/`: HTTP API endpoints
- `graphql/`: GraphQL API interface

**engine/**: Agent execution engine
- `agent/`: Base agent classes and implementations (RAG, LLM calls, tools)
- `graph_runner/`: Workflow execution with NetworkX graphs
- `llm_services/`: LLM provider abstractions
- `trace/`: Distributed tracing and monitoring

**data_ingestion/**: Document processing pipeline
- `document/`: PDF, Excel, Word, Markdown processors
- `markdown/`: Tree-based chunking for structured documents
- `folder_management/`: S3, Google Drive integrations

### Key Design Patterns

1. **Dynamic Component Instantiation**: Components are registered in `services/registry.py` and instantiated dynamically using factories
2. **Graph-Based Workflows**: Agents are composed into DAGs executed by `GraphRunner`
3. **Tracing**: All operations are traced using OpenTelemetry for observability
4. **Multi-Database**: Separate databases for backend, ingestion, and traces

### Authentication & Security

- **Supabase**: User authentication and organization management
- **API Keys**: RSA key-pair system for project-scoped access
- **Encrypted Secrets**: Organization secrets stored with Fernet encryption
- **JWT**: Internal token system separate from Supabase tokens

## Development Workflow

### Adding New Components

1. Define component in `ada_backend/database/models.py`
2. Register factory in `ada_backend/services/registry.py`
3. Implement component class in `engine/agent/`
4. Add database seed data in `ada_backend/database/seed/`
5. Create tests in `tests/`

### Database Changes

1. Create migration: `make db-revision message="description"`
2. Apply migration: `make db-upgrade`
3. Update seed data if needed
4. Test migration rollback: `make db-downgrade`

### Testing Strategy

- **Unit Tests**: Mock database operations using `tests/mocks/`
- **Integration Tests**: Use seeded database via `seed_db.py`
- **Coverage**: Minimum 10% coverage enforced
- **Quality**: Black formatting + flake8 linting required

## Configuration

### Environment Files Required

1. `credentials.env` (root): Main configuration
2. `ada_ingestion_system/.env`: Worker configuration
3. `config/seaweedfs/s3_config.json`: S3 storage configuration

### Database Configuration

- **SQLite**: Set `ADA_DB_URL=sqlite:///path/to/db.sqlite`
- **PostgreSQL**: Set individual connection parameters or full URL

### Custom LLM Models

Add custom models via environment variables:
```env
CUSTOM_LLM_MODELS={"provider": {"model_name": ["model1", "model2"], "base_url": "https://api.example.com", "api_key": "key"}}
CUSTOM_EMBEDDING_MODELS={"provider": {"model_name": ["embed1"], "base_url": "https://embed.example.com", "api_key": "key"}}
```

## Key Files and Locations

- **Main Entry**: `ada_backend/main.py`
- **Settings**: `settings.py` (Pydantic settings with env file support)
- **Database Models**: `ada_backend/database/models.py`
- **Component Registry**: `ada_backend/services/registry.py`
- **Agent Base**: `engine/agent/agent.py`
- **Graph Runner**: `engine/graph_runner/graph_runner.py`
- **Tracing**: `engine/trace/trace_manager.py`
- **Admin Interface**: `ada_backend/admin/admin.py`

## Common Patterns

### Error Handling
All agents inherit from `Agent` base class with automatic tracing and error handling via OpenTelemetry spans.

### Logging
Use structured logging with the logger setup in `logger.py`:
```python
import logging
LOGGER = logging.getLogger(__name__)
```

### Async Operations
Most operations are async. Use `asyncio.run()` for sync interfaces when needed.

### Database Sessions
Use dependency injection for database sessions in FastAPI routes.

## Admin Interface

Access at `http://localhost:8000/admin` with `ADMIN_USERNAME`/`ADMIN_PASSWORD` credentials. Provides GUI for managing components, instances, and relationships.

API Documentation available at `http://localhost:8000/docs`.