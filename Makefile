# -------------------------------------------
# Help and Meta Commands
# -------------------------------------------
.PHONY: help
help:
	@echo "test: Run the tests with coverage."
	@echo "format: Format the code using Black."
	@echo "quality-check: Check the code quality using flake8 and Black."
	@echo "pre-push: Run tests and quality checks before pushing code."

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
	@uv run ruff format .

.PHONY: quality-check
quality-check:
	uv run ruff check .

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
