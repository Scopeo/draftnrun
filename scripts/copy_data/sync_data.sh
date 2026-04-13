#!/bin/bash
set -e

# Syncs data from source to target databases (with TTL cache)
# Only runs dump + restore (and optional Qdrant sync) if cache is expired (24h)
# TTL source of truth: ada_backend.latest.dump
#
# Modes:
#   --skip-qdrant   Sync DBs only, skip Qdrant
#   --only-qdrant   Sync Qdrant only, skip DBs and TTL check
#   (default)       Sync both DBs and Qdrant
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
#     [--force-sync] [--skip-qdrant] [--only-qdrant]

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
  [--force-sync] \\
  [--skip-qdrant] \\
  [--only-qdrant]
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
SKIP_QDRANT=0
ONLY_QDRANT=0

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
    --skip-qdrant)
      SKIP_QDRANT=1; shift 1 ;;
    --only-qdrant)
      ONLY_QDRANT=1; shift 1 ;;
    -h|--help)
      print_usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage
      exit 1 ;;
  esac
done

if [ "$SKIP_QDRANT" = "1" ] && [ "$ONLY_QDRANT" = "1" ]; then
  echo "ERROR: --skip-qdrant and --only-qdrant are mutually exclusive." >&2
  exit 1
fi

# Validate required flags based on mode
if [ "$ONLY_QDRANT" = "1" ]; then
  if [ -z "$SOURCE_QDRANT_CLUSTER_URL" ] || [ -z "$SOURCE_QDRANT_API_KEY" ] || \
     [ -z "$TARGET_QDRANT_CLUSTER_URL" ] || [ -z "$TARGET_QDRANT_API_KEY" ] || \
     [ -z "$SOURCE_DB_URL" ]; then
    echo "ERROR: --only-qdrant requires all Qdrant flags and --source-db-url." >&2
    print_usage
    exit 1
  fi
else
  if [ -z "$SOURCE_DB_URL" ] || [ -z "$SOURCE_INGESTION_DB_URL" ] || \
     [ -z "$TARGET_DB_URL" ] || [ -z "$TARGET_INGESTION_DB_URL" ]; then
    echo "ERROR: Missing required database URLs." >&2
    print_usage
    exit 1
  fi
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
      return 1
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

sync_qdrant() {
  if [ -z "$SOURCE_QDRANT_CLUSTER_URL" ] || [ -z "$SOURCE_QDRANT_API_KEY" ] || \
     [ -z "$TARGET_QDRANT_CLUSTER_URL" ] || [ -z "$TARGET_QDRANT_API_KEY" ]; then
    echo "===> Qdrant flags not fully set, skipping Qdrant sync"
    return 0
  fi

  echo "===> Syncing Qdrant collections"
  python scripts/copy_data/copy_qdrant_collections.py \
    --source-url="$SOURCE_QDRANT_CLUSTER_URL" \
    --source-key="$SOURCE_QDRANT_API_KEY" \
    --target-url="$TARGET_QDRANT_CLUSTER_URL" \
    --target-key="$TARGET_QDRANT_API_KEY" \
    --source-db-url="$SOURCE_DB_URL"
  echo "===> Qdrant sync completed"
  return 0
}

if [ "$ONLY_QDRANT" = "1" ]; then
  sync_qdrant
elif [ "$SKIP_QDRANT" = "1" ]; then
  sync_databases || true
else
  if sync_databases; then
    sync_qdrant
  fi
fi

