#!/bin/bash
set -e

# Syncs data from source to target databases (with TTL cache)
# Only runs dump + restore (and optional Qdrant sync) if cache is expired (24h)
# TTL source of truth: ada_backend.latest.dump
#
# Usage:
#   ./sync_data.sh \\
#     --source-db-url              postgres://... \\
#     --source-ingestion-db-url    postgres://... \\
#     --target-db-url              postgres://... \\
#     --target-ingestion-db-url    postgres://... \\
#     [--source-qdrant-url         https://... ] \\
#     [--source-qdrant-key         xxx ] \\
#     [--target-qdrant-url         https://... ] \\
#     [--target-qdrant-key         xxx ] \\
#     [--force-sync]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/db_utils.sh"

print_usage() {
  cat >&2 <<EOF
Usage: ./sync_data.sh \\
  --source-db-url              postgres://... \\
  --source-ingestion-db-url    postgres://... \\
  --target-db-url              postgres://... \\
  --target-ingestion-db-url    postgres://... \\
  [--source-qdrant-url         https://...] \\
  [--source-qdrant-key         xxx] \\
  [--target-qdrant-url         https://...] \\
  [--target-qdrant-key         xxx] \\
  [--force-sync]
EOF
}

# Defaults
SOURCE_DB_URL=""
SOURCE_INGESTION_DB_URL=""
TARGET_DB_URL=""
TARGET_INGESTION_DB_URL=""
SOURCE_QDRANT_CLUSTER_URL=""
SOURCE_QDRANT_API_KEY=""
TARGET_QDRANT_CLUSTER_URL=""
TARGET_QDRANT_API_KEY=""
FORCE_SYNC="${FORCE_SYNC:-0}"

# Parse flags
while [ $# -gt 0 ]; do
  case "$1" in
    --source-db-url)
      SOURCE_DB_URL="$2"; shift 2 ;;
    --source-ingestion-db-url)
      SOURCE_INGESTION_DB_URL="$2"; shift 2 ;;
    --target-db-url)
      TARGET_DB_URL="$2"; shift 2 ;;
    --target-ingestion-db-url)
      TARGET_INGESTION_DB_URL="$2"; shift 2 ;;
    --source-qdrant-url)
      SOURCE_QDRANT_CLUSTER_URL="$2"; shift 2 ;;
    --source-qdrant-key)
      SOURCE_QDRANT_API_KEY="$2"; shift 2 ;;
    --target-qdrant-url)
      TARGET_QDRANT_CLUSTER_URL="$2"; shift 2 ;;
    --target-qdrant-key)
      TARGET_QDRANT_API_KEY="$2"; shift 2 ;;
    --force-sync)
      FORCE_SYNC=1; shift 1 ;;
    -h|--help)
      print_usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage
      exit 1 ;;
  esac
done

# Validate required DB flags
if [ -z "$SOURCE_DB_URL" ] || [ -z "$SOURCE_INGESTION_DB_URL" ] || \
   [ -z "$TARGET_DB_URL" ] || [ -z "$TARGET_INGESTION_DB_URL" ]; then
  echo "ERROR: Missing required database URLs." >&2
  print_usage
  exit 1
fi

echo "===> Checking if sync is needed (TTL 24h, based on ada_backend dump only)"

# Single TTL source of truth: ada_backend.latest.dump
# FORCE_SYNC=1 (or --force-sync) will skip TTL and force a full sync (DBs + Qdrant)
if [ "$FORCE_SYNC" != "1" ]; then
  if check_dump_ttl "$BACKEND_DUMP_PATH" "ada_backend"; then
    echo "===> Cache valid based on ada_backend dump, nothing to do"
    exit 0
  fi
else
  echo "===> FORCE_SYNC enabled, skipping TTL check and forcing full sync"
fi

echo "===> Cache expired or missing (based on ada_backend) or forced, starting sync process"

# Ensure PostgreSQL tools are installed
ensure_pg_tools

# Sync ada_backend: dump, drop/create, and restore
echo "===> Dumping ada_backend from source"
pg_dump -Fc "$SOURCE_DB_URL" -f "$BACKEND_DUMP_PATH"
drop_and_create_db "$TARGET_DB_URL" "ada_backend"
echo "===> Restoring ada_backend"
pg_restore -d "$TARGET_DB_URL" --no-owner --no-privileges --single-transaction --verbose -Fc "$BACKEND_DUMP_PATH"

# Deactivate all cron jobs in staging database
echo "===> Deactivating all cron jobs in staging database"
DEACTIVATED_COUNT=$(psql "$TARGET_DB_URL" -t -A -c "
  WITH updated AS (
    UPDATE scheduler.cron_jobs 
    SET is_enabled = false 
    WHERE is_enabled = true 
    RETURNING id
  )
  SELECT COUNT(*) FROM updated;
" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$DEACTIVATED_COUNT" != "0" ] && [ "$DEACTIVATED_COUNT" != "" ]; then
  echo "===> Deactivated $DEACTIVATED_COUNT cron job(s) in staging database"
else
  # Check if schema exists to provide better error message
  SCHEMA_EXISTS=$(psql "$TARGET_DB_URL" -t -A -c "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'scheduler');" 2>/dev/null | tr -d ' ' || echo "f")
  if [ "$SCHEMA_EXISTS" = "t" ]; then
    echo "===> No enabled cron jobs found to deactivate"
  else
    echo "===> Scheduler schema not found, skipping cron job deactivation"
  fi
fi

# Sync ada_ingestion: dump, drop/create, and restore
echo "===> Dumping ada_ingestion from source"
pg_dump -Fc "$SOURCE_INGESTION_DB_URL" -f "$INGESTION_DUMP_PATH"
drop_and_create_db "$TARGET_INGESTION_DB_URL" "ada_ingestion"
echo "===> Restoring ada_ingestion"
pg_restore -d "$TARGET_INGESTION_DB_URL" --no-owner --no-privileges --single-transaction --verbose -Fc "$INGESTION_DUMP_PATH"

# Sync Qdrant collections (if configured)
if command -v uv >/dev/null 2>&1; then
  if [ -n "$SOURCE_QDRANT_CLUSTER_URL" ] && [ -n "$SOURCE_QDRANT_API_KEY" ] && \
     [ -n "$TARGET_QDRANT_CLUSTER_URL" ] && [ -n "$TARGET_QDRANT_API_KEY" ]; then
    echo "===> Syncing Qdrant collections"
    # Use SOURCE_DB_URL to read collections from source database (prod)
    uv run scripts/copy_data/copy_qdrant_collections.py \
      --source-url="$SOURCE_QDRANT_CLUSTER_URL" \
      --source-key="$SOURCE_QDRANT_API_KEY" \
      --target-url="$TARGET_QDRANT_CLUSTER_URL" \
      --target-key="$TARGET_QDRANT_API_KEY" \
      --source-db-url="$SOURCE_DB_URL"
  else
    echo "===> Qdrant flags not fully set, skipping Qdrant sync"
  fi
else
  echo "===> uv not found in PATH, skipping Qdrant sync"
fi

echo "===> Sync completed"

