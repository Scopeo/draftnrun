#!/bin/bash
set -eo pipefail

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

pipe_dump_restore() {
  local source_url="$1"
  local target_url="$2"
  local db_name="$3"

  echo "===> [$db_name] Preparing target database"
  drop_and_create_db "$target_url" "$db_name"

  echo "===> [$db_name] Streaming pg_dump → pg_restore"
  pg_dump -Fc "$source_url" | pg_restore -d "$target_url" --no-owner --no-privileges -Fc
  echo "===> [$db_name] Done"
}

deactivate_staging_crons() {
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
}

sync_databases() {
  if [ "$FORCE_SYNC" != "1" ]; then
    if check_dump_ttl "$BACKEND_DUMP_PATH" "ada_backend"; then
      echo "===> Cache valid based on ada_backend dump, nothing to do"
      return 0
    fi
  else
    echo "===> FORCE_SYNC enabled, skipping TTL check"
  fi

  ensure_pg_tools

  echo "===> Starting parallel database sync (ada_backend + ada_ingestion)"

  (pipe_dump_restore "$SOURCE_DB_URL" "$TARGET_DB_URL" "ada_backend" && deactivate_staging_crons) &
  local backend_pid=$!

  pipe_dump_restore "$SOURCE_INGESTION_DB_URL" "$TARGET_INGESTION_DB_URL" "ada_ingestion" &
  local ingestion_pid=$!

  local failed=0
  wait $backend_pid || { echo "===> ERROR: ada_backend sync failed"; failed=1; }
  wait $ingestion_pid || { echo "===> ERROR: ada_ingestion sync failed"; failed=1; }

  if [ "$failed" = "1" ]; then
    echo "===> Database sync FAILED"
    exit 1
  fi

  touch "$BACKEND_DUMP_PATH"
  echo "===> Database sync completed"
  return 0
}

sync_databases
