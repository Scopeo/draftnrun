# Use Python 3.11 base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code (excluding what's in .dockerignore)
COPY . .

# Expose port (Railway will override this with $PORT)
EXPOSE 8000

# Run database migrations and start the application
CMD uv run alembic -c engine/trace/alembic.ini upgrade head && \
    uv run alembic -c ada_backend/database/alembic.ini upgrade head && \
    uv run python -m ada_backend.database.seed_db && \
    uv run gunicorn -w 2 -k uvicorn.workers.UvicornWorker ada_backend.main:app --bind 0.0.0.0:${PORT:-8000}

