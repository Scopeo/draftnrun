#!/bin/bash
# Clean QA projects data from preprod database
#
# This script deletes all data related to the QA organization from preprod
# in the correct order to respect foreign key constraints.

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
PREPROD_URL="${PREPROD_DATABASE_URL:-}"
ORG_ID="${QA_ORG_ID:-18012b84-b605-4669-95bf-55aa16c5513c}"

# Validate required environment variables
if [ -z "$PREPROD_URL" ]; then
    echo -e "${RED}ERROR: PREPROD_DATABASE_URL environment variable is not set!${NC}"
    echo ""
    echo "Please set it before running this script:"
    echo "  export PREPROD_DATABASE_URL='postgresql://user:pass@host:port/database'"
    exit 1
fi

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Clean Preprod Data for QA Projects${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "Organization ID: $ORG_ID"
echo ""
echo -e "${RED}WARNING: This will delete all QA organization data from preprod!${NC}"
echo -e "${YELLOW}Press Enter to continue or Ctrl+C to cancel...${NC}"
read

# Function to count rows before deletion
count_rows() {
    local table=$1
    local where_clause=$2
    
    local count=$(psql "$PREPROD_URL" -t -c "SELECT COUNT(*) FROM $table WHERE $where_clause" | tr -d ' ')
    echo "$count"
}

# Function to delete rows from a table
delete_from_table() {
    local table=$1
    local where_clause=$2
    
    echo -e "${YELLOW}Cleaning $table...${NC}"
    
    local before_count=$(count_rows "$table" "$where_clause")
    
    if [ "$before_count" -gt 0 ]; then
        psql "$PREPROD_URL" -c "DELETE FROM $table WHERE $where_clause" > /dev/null
        echo -e "${GREEN}✓ Deleted $before_count rows from $table${NC}"
    else
        echo -e "${YELLOW}⚠ No rows to delete from $table${NC}"
    fi
}

echo ""
echo -e "${GREEN}Step 1: Delete configuration data (leaf nodes in dependency graph)${NC}"

delete_from_table "component_sub_inputs" \
    "parent_component_instance_id IN (
        SELECT ci.id FROM component_instances ci
        JOIN graph_runner_nodes grn ON ci.id = grn.node_id
        JOIN graph_runners gr ON grn.graph_runner_id = gr.id
        JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
        JOIN projects p ON peb.project_id = p.id
        WHERE p.organization_id = '$ORG_ID'
    )"

delete_from_table "port_mappings" \
    "graph_runner_id IN (
        SELECT gr.id FROM graph_runners gr
        JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
        JOIN projects p ON peb.project_id = p.id
        WHERE p.organization_id = '$ORG_ID'
    )"

delete_from_table "basic_parameters" \
    "component_instance_id IN (
        SELECT ci.id FROM component_instances ci
        JOIN graph_runner_nodes grn ON ci.id = grn.node_id
        JOIN graph_runners gr ON grn.graph_runner_id = gr.id
        JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
        JOIN projects p ON peb.project_id = p.id
        WHERE p.organization_id = '$ORG_ID'
    )"

echo ""
echo -e "${GREEN}Step 2: Delete graph structure${NC}"

delete_from_table "graph_runner_edges" \
    "graph_runner_id IN (
        SELECT gr.id FROM graph_runners gr
        JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
        JOIN projects p ON peb.project_id = p.id
        WHERE p.organization_id = '$ORG_ID'
    )"

delete_from_table "graph_runner_nodes" \
    "graph_runner_id IN (
        SELECT gr.id FROM graph_runners gr
        JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
        JOIN projects p ON peb.project_id = p.id
        WHERE p.organization_id = '$ORG_ID'
    )"

echo ""
echo -e "${GREEN}Step 3: Delete component instances (before deleting bindings)${NC}"

delete_from_table "component_instances" \
    "id IN (
        SELECT ci.id FROM component_instances ci
        JOIN graph_runner_nodes grn ON ci.id = grn.node_id
        JOIN graph_runners gr ON grn.graph_runner_id = gr.id
        JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
        JOIN projects p ON peb.project_id = p.id
        WHERE p.organization_id = '$ORG_ID'
    )"

echo ""
echo -e "${GREEN}Step 4: Delete graph runners (before deleting bindings)${NC}"

delete_from_table "graph_runners" \
    "id IN (
        SELECT gr.id FROM graph_runners gr
        JOIN project_env_binding peb ON gr.id = peb.graph_runner_id
        JOIN projects p ON peb.project_id = p.id
        WHERE p.organization_id = '$ORG_ID'
    )"

echo ""
echo -e "${GREEN}Step 5: Delete project bindings${NC}"

delete_from_table "project_env_binding" \
    "project_id IN (
        SELECT id FROM projects WHERE organization_id = '$ORG_ID'
    )"

echo ""
echo -e "${GREEN}Step 6: Delete polymorphic project tables${NC}"

delete_from_table "workflow_projects" \
    "id IN (
        SELECT id FROM projects WHERE organization_id = '$ORG_ID'
    )"

delete_from_table "agent_projects" \
    "id IN (
        SELECT id FROM projects WHERE organization_id = '$ORG_ID'
    )"

echo ""
echo -e "${GREEN}Step 7: Delete projects (base table)${NC}"

delete_from_table "projects" \
    "organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Cleanup Complete!${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "Preprod is now clean and ready for import."
echo ""
echo "Next step: Run 03_import_preprod_data.sh"

