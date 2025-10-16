#!/bin/bash
# QA Migration: Add QA projects from staging to preprod
# Assumes preprod already has prod data + proper schema
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_URL="${STAGING_DATABASE_URL:-}"
PREPROD_URL="${PREPROD_DATABASE_URL:-}"
ORG_ID="${QA_ORG_ID:-18012b84-b605-4669-95bf-55aa16c5513c}"

if [ -z "$STAGING_URL" ] || [ -z "$PREPROD_URL" ]; then
    echo "ERROR: Set STAGING_DATABASE_URL and PREPROD_DATABASE_URL"
    exit 1
fi

echo "=== QA Migration: Staging → Preprod ==="
echo "Adding QA projects to preprod (on top of prod data)"
echo ""

# 1. Export from staging
echo "1. Exporting QA projects from staging..."
bash "$SCRIPT_DIR/01_export_staging_data.sh"

# 2. Import to preprod
echo ""
echo "2. Importing QA projects to preprod..."
bash "$SCRIPT_DIR/03_import_preprod_data.sh"

# 3. Validate
echo ""
echo "3. Validating migration..."
bash "$SCRIPT_DIR/04_validate_migration.sh"

echo ""
echo "✓ Migration complete!"
echo ""
echo "QA projects from staging are now in preprod alongside prod data."

