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
TRUNCATE TABLE component_sub_inputs, port_mappings, basic_parameters, 
                graph_runner_edges, graph_runner_nodes, project_env_binding,
                component_instances, graph_runners, workflow_projects, 
                agent_projects, projects CASCADE;
EOF

echo "✓ All tables truncated"
echo ""
echo "Now run Alembic migrations and seed database:"
echo "  cd /home/ec2-user/draftnrun"
echo "  make db-upgrade"
echo "  make db-seed"

