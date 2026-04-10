#!/bin/bash
set -e

# Syncs data from source to target databases (with TTL cache)
# Only runs dump + restore if cache is expired (24h)
# TTL source of truth: ada_backend.latest.dump
#
# Qdrant sync is handled separately via qdrant-migration Docker image
# (see .github/workflows/sync-prod-to-staging.yml)
#
# Usage:
#   ./sync_data.sh \\
#     --source-db-url              postgres://... \\
#     --source-ingestion-db-url    postgres://... \\
#     --target-db-url              postgres://... \\
#     --target-ingestion-db-url    postgres://... \\
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
  [--force-sync]
EOF
}

SOURCE_DB_URL=""
SOURCE_INGESTION_DB_URL=""
TARGET_DB_URL=""
TARGET_INGESTION_DB_URL=""
FORCE_SYNC="${FORCE_SYNC:-0}"

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
    --force-sync)
      FORCE_SYNC=1; shift 1 ;;
    --skip-qdrant)
      shift 1 ;;
    -h|--help)
      print_usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage
      exit 1 ;;
  esac
done

if [ -z "$SOURCE_DB_URL" ] || [ -z "$SOURCE_INGESTION_DB_URL" ] || \
   [ -z "$TARGET_DB_URL" ] || [ -z "$TARGET_INGESTION_DB_URL" ]; then
  echo "ERROR: Missing required database URLs." >&2
  print_usage
  exit 1
fi

sync_databases() {
  echo "===> Checking if sync is needed (TTL 24h, based on ada_backend dump only)"

  if [ "$FORCE_SYNC" != "1" ]; then
    if check_dump_ttl "$BACKEND_DUMP_PATH" "ada_backend"; then
      echo "===> Cache valid based on ada_backend dump, nothing to do"
      return 1
    fi
  else
    echo "===> FORCE_SYNC enabled, skipping TTL check and forcing full sync"
  fi

  echo "===> Cache expired or missing (based on ada_backend) or forced, starting sync process"

  ensure_pg_tools

  echo "===> Dumping ada_backend from source"
  pg_dump -Fc "$SOURCE_DB_URL" -f "$BACKEND_DUMP_PATH"
  drop_and_create_db "$TARGET_DB_URL" "ada_backend"
  echo "===> Restoring ada_backend"
  pg_restore -d "$TARGET_DB_URL" --no-owner --no-privileges --single-transaction --verbose -Fc "$BACKEND_DUMP_PATH"

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
    SCHEMA_EXISTS=$(psql "$TARGET_DB_URL" -t -A -c "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'scheduler');" 2>/dev/null | tr -d ' ' || echo "f")
    if [ "$SCHEMA_EXISTS" = "t" ]; then
      echo "===> No enabled cron jobs found to deactivate"
    else
      echo "===> Scheduler schema not found, skipping cron job deactivation"
    fi
  fi

  echo "===> Dumping ada_ingestion from source"
  pg_dump -Fc "$SOURCE_INGESTION_DB_URL" -f "$INGESTION_DUMP_PATH"
  drop_and_create_db "$TARGET_INGESTION_DB_URL" "ada_ingestion"
  echo "===> Restoring ada_ingestion"
  pg_restore -d "$TARGET_INGESTION_DB_URL" --no-owner --no-privileges --single-transaction --verbose -Fc "$INGESTION_DUMP_PATH"

  echo "===> Database sync completed"
  return 0
}

sync_databases || true

