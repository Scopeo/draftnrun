#!/bin/bash
# TESTING ONLY: Truncate preprod tables to simulate clean slate
# DO NOT USE in real migration - prod data will already be there
set -e

PREPROD_URL="${PREPROD_DATABASE_URL:-}"

if [ -z "$PREPROD_URL" ]; then
    echo "ERROR: Set PREPROD_DATABASE_URL"
    exit 1
fi

echo "=== TRUNCATE PREPROD (TESTING ONLY) ==="
echo ""
echo "WARNING: This deletes ALL data from preprod!"
echo "Type 'YES' to confirm:"
read confirmation

if [ "$confirmation" != "YES" ]; then
    echo "Cancelled."
    exit 0
fi

psql "$PREPROD_URL" << 'EOF'
-- Drop all schemas and recreate
DROP SCHEMA IF EXISTS public CASCADE;
DROP SCHEMA IF EXISTS scheduler CASCADE;
DROP SCHEMA IF EXISTS quality_assurance CASCADE;

-- Recreate schemas
CREATE SCHEMA public;
CREATE SCHEMA scheduler;
CREATE SCHEMA quality_assurance;

-- Grant permissions
GRANT ALL ON SCHEMA public TO ada_preprod_user;
GRANT ALL ON SCHEMA public TO public;
GRANT ALL ON SCHEMA scheduler TO ada_preprod_user;
GRANT ALL ON SCHEMA quality_assurance TO ada_preprod_user;
EOF

echo "✓ All tables truncated"
echo ""
echo "Now run Alembic migrations and seed database:"
echo "  cd /home/ec2-user/draftnrun"
echo "  make db-upgrade"
echo "  make db-seed"

