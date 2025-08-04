# -------------------------------------------
# Help and Meta Commands
# -------------------------------------------
.PHONY: help
help:
	@echo "test: Run the tests with coverage."
	@echo "format: Format the code using Black."
	@echo "quality-check: Check the code quality using flake8 and Black."
	@echo "pre-push: Run tests and quality checks before pushing code."
	@echo "run-celery-worker: Start the Celery worker for background tasks."
	@echo "run-celery-beat: Start the Celery beat scheduler for cron jobs."
	@echo "run-celery-worker-debug: Start the Celery worker in debug mode."
	@echo "run-celery-beat-debug: Start the Celery beat scheduler in debug mode."
	@echo ""
	@echo "Database Commands:"
	@echo "  db-upgrade: Apply database migrations"
	@echo "  db-downgrade: Revert last migration"
	@echo "  db-current: Check current migration"
	@echo "  db-history: Show migration history"
	@echo ""
	@echo "Cron Database Commands:"
	@echo "  cron-db-setup: Setup django-celery-beat tables in custom schema"
	@echo ""
	@echo "Test Commands:"
	@echo "  test-celery-setup: Setup test schedules for celery beat testing"
	@echo "  test-celery-cleanup: Clean up test schedules"
	@echo "  test-celery-list: List current schedules"
	@echo "  test-api-key-integration: Test API key integration in deployment process"
	@echo "  test-complete-integration: Test complete API key lifecycle integration"
	@echo "  test-project-deletion-cleanup: Test project deletion API key cleanup"
	@echo "  debug-schedules: Debug schedules for a project (use: make debug-schedules project_id=<uuid>)"
	@echo "  cleanup-orphaned-schedules: Clean up orphaned schedules (use: make cleanup-orphaned-schedules project_id=<uuid>)"
	@echo "  verify-celery-tasks: Verify Celery task registration and consistency"

# -------------------------------------------
# Development and Running
# -------------------------------------------
.PHONY: run-draftnrun-agents-backend
run-draftnrun-agents-backend:
	@echo "Running draftnrun agents backend"
	@uv run python -m ada_backend.main

.PHONY: run-backend-prod
run-backend-prod:
	@echo "Running Ada in production"
	@uv run gunicorn -w 2 -k uvicorn.workers.UvicornWorker ada_backend.main:app

# -------------------------------------------
# Testing and Quality
# -------------------------------------------
.PHONY: test
test:
	@echo "Running Tests"
	@uv run coverage run -m pytest

.PHONY: format
format:
	@echo "Formatting Code"
	@uv run black .

.PHONY: quality-check
quality-check:
	uv run flake8 .
	uv run black --check .

.PHONY: pre-push
pre-push: test quality-check
	@echo "All checks passed. Ready to push."

# -------------------------------------------
# Backend Utilities
# -------------------------------------------
.PHONY: generate-fernet-key
generate-fernet-key:
	@echo "Generating Fernet key"
	@uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

.PHONY: generate-backend-secret-key
generate-backend-secret-key:
	@echo "Generating backend secret key"
	@uv run python -c "import secrets; print(secrets.token_hex(32))"

.PHONY: get-supabase-token
get-supabase-token:
	@echo "Fetching Supabase token for username $(username)"
	@uv run python -m ada_backend.scripts.get_supabase_token --username $(username) --password $(password)

# -------------------------------------------
# Celery Commands
# -------------------------------------------
.PHONY: run-celery-worker
run-celery-worker:
	@echo "Starting Celery worker"
	@uv run celery -A ada_backend.celery_app worker --loglevel=info

.PHONY: run-celery-beat
run-celery-beat:
	@echo "Starting Celery beat scheduler"
	@uv run celery -A ada_backend.celery_app beat --loglevel=info

.PHONY: run-celery-worker-debug
run-celery-worker-debug:
	@echo "Starting Celery worker in debug mode"
	@uv run celery -A ada_backend.celery_app worker --loglevel=debug

.PHONY: run-celery-beat-debug
run-celery-beat-debug:
	@echo "Starting Celery beat scheduler in debug mode"
	@uv run celery -A ada_backend.celery_app beat --loglevel=debug

# -------------------------------------------
# Database Migrations (Alembic)
# -------------------------------------------
ALEMBIC_CMD = uv run alembic -c ada_backend/database/alembic.ini

.PHONY: db-revision
db-revision:
	@echo "Creating a new migration"
	@$(ALEMBIC_CMD) revision --autogenerate -m "$(message)"

.PHONY: db-upgrade
db-upgrade:
	@echo "Applying migrations"
	@$(ALEMBIC_CMD) upgrade head

.PHONY: db-downgrade
db-downgrade:
	@echo "Reverting last migration"
	@$(ALEMBIC_CMD) downgrade -1

.PHONY: db-history
db-history:
	@echo "Showing migration history"
	@$(ALEMBIC_CMD) history

.PHONY: db-current
db-current:
	@echo "Checking current migration"
	@$(ALEMBIC_CMD) current

.PHONY: db-seed
db-seed:
	@echo "Seeding database"
	@uv run python -m ada_backend.database.seed_db

.PHONY: db-reset
db-reset:
	@echo "Warning: This is a Dev only command. It will drop the database and recreate it."
	@read -p "Are you sure you want to continue? (y/N): " confirm; \
	if [ "$$confirm" != "y" ]; then \
		echo "Aborting."; \
		exit 1; \
	fi
	@echo "Closing all existing connections to the database..."
	@docker exec -it ada_postgres psql -U ada_user -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'ada_backend' AND pid <> pg_backend_pid();"
	@docker exec -it ada_postgres psql -U ada_user -d postgres -c "DROP DATABASE IF EXISTS ada_backend;" && docker exec -it ada_postgres psql -U ada_user -d postgres -c "CREATE DATABASE ada_backend;"

# -------------------------------------------
# Cron Database Setup
# -------------------------------------------
.PHONY: cron-db-setup
cron-db-setup:
	@echo "Setting up django-celery-beat tables in custom schema"
	@uv run python ada_backend/scripts/setup_django_beat_schema.py

# -------------------------------------------
# Test Commands
# -------------------------------------------
.PHONY: test-celery-setup
test-celery-setup:
	@echo "Setting up test schedules for celery beat testing"
	@uv run python ada_backend/scripts/test_celery_beat_setup.py setup

.PHONY: test-celery-cleanup
test-celery-cleanup:
	@echo "Cleaning up test schedules"
	@uv run python ada_backend/scripts/test_celery_beat_setup.py cleanup

.PHONY: test-celery-list
test-celery-list:
	@echo "Listing current schedules"
	@uv run python ada_backend/scripts/test_celery_beat_setup.py list

.PHONY: test-api-key-integration
test-api-key-integration:
	@echo "Testing API key integration in deployment process"
	@uv run python ada_backend/scripts/test_api_key_integration.py

.PHONY: test-complete-integration
test-complete-integration:
	@echo "Testing complete API key lifecycle integration"
	@uv run python ada_backend/scripts/test_complete_integration.py

.PHONY: test-project-deletion-cleanup
test-project-deletion-cleanup:
	@echo "Testing project deletion API key cleanup"
	@uv run python ada_backend/scripts/test_project_deletion_api_key_cleanup.py

# -------------------------------------------
# Trace Database Migrations (Alembic)
# -------------------------------------------
TRACE_ALEMBIC_CMD = uv run alembic -c engine/trace/alembic.ini

.PHONY: trace-db-revision
trace-db-revision:
	@echo "Creating a new migration"
	@$(TRACE_ALEMBIC_CMD) revision --autogenerate -m "$(message)"

.PHONY: trace-db-upgrade
trace-db-upgrade:
	@echo "Applying migrations"
	@$(TRACE_ALEMBIC_CMD) upgrade head

.PHONY: trace-db-downgrade
trace-db-downgrade:
	@echo "Reverting last migration"
	@$(TRACE_ALEMBIC_CMD) downgrade -1

.PHONY: trace-db-history
trace-db-history:
	@echo "Showing migration history"
	@$(TRACE_ALEMBIC_CMD) history

.PHONY: trace-db-current
trace-db-current:
	@echo "Checking current migration"
	@$(TRACE_ALEMBIC_CMD) current

.PHONY: cleanup-orphaned-schedules
cleanup-orphaned-schedules:
	@echo "Cleaning up orphaned schedules for project $(project_id)"
	@uv run python ada_backend/scripts/debug_schedules.py cleanup $(project_id) --dry-run

.PHONY: verify-celery-tasks
verify-celery-tasks:
	@echo "Verifying Celery task registration and consistency"
	@uv run python ada_backend/scripts/verify_celery_tasks.py
