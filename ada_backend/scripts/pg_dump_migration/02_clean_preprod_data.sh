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
echo -e "${GREEN}Step 8: Cleanup any orphaned records (safety net)${NC}"

# Clean up any orphaned basic_parameters first (depend on component_instances)
echo -e "${YELLOW}Cleaning orphaned basic_parameters (if any)...${NC}"
ORPHANED_BP=$(psql "$PREPROD_URL" -t -c "SELECT COUNT(*) FROM basic_parameters WHERE component_instance_id NOT IN (SELECT DISTINCT id FROM component_instances)" | tr -d ' ')
if [ "$ORPHANED_BP" -gt 0 ]; then
    psql "$PREPROD_URL" -c "DELETE FROM basic_parameters WHERE component_instance_id NOT IN (SELECT DISTINCT id FROM component_instances)" > /dev/null
    echo -e "${GREEN}✓ Deleted $ORPHANED_BP orphaned basic_parameters${NC}"
else
    echo -e "${YELLOW}⚠ No orphaned basic_parameters found${NC}"
fi

# Clean up any orphaned port_mappings (depend on graph_runners)
echo -e "${YELLOW}Cleaning orphaned port_mappings (if any)...${NC}"
ORPHANED_PM=$(psql "$PREPROD_URL" -t -c "SELECT COUNT(*) FROM port_mappings WHERE graph_runner_id NOT IN (SELECT DISTINCT id FROM graph_runners)" | tr -d ' ')
if [ "$ORPHANED_PM" -gt 0 ]; then
    psql "$PREPROD_URL" -c "DELETE FROM port_mappings WHERE graph_runner_id NOT IN (SELECT DISTINCT id FROM graph_runners)" > /dev/null
    echo -e "${GREEN}✓ Deleted $ORPHANED_PM orphaned port_mappings${NC}"
else
    echo -e "${YELLOW}⚠ No orphaned port_mappings found${NC}"
fi

# Clean up any orphaned component_sub_inputs (depend on component_instances)
echo -e "${YELLOW}Cleaning orphaned component_sub_inputs (if any)...${NC}"
ORPHANED_CSI=$(psql "$PREPROD_URL" -t -c "SELECT COUNT(*) FROM component_sub_inputs WHERE parent_component_instance_id NOT IN (SELECT DISTINCT id FROM component_instances)" | tr -d ' ')
if [ "$ORPHANED_CSI" -gt 0 ]; then
    psql "$PREPROD_URL" -c "DELETE FROM component_sub_inputs WHERE parent_component_instance_id NOT IN (SELECT DISTINCT id FROM component_instances)" > /dev/null
    echo -e "${GREEN}✓ Deleted $ORPHANED_CSI orphaned component_sub_inputs${NC}"
else
    echo -e "${YELLOW}⚠ No orphaned component_sub_inputs found${NC}"
fi

# Clean up any orphaned graph_runner_edges (depend on graph_runners)
echo -e "${YELLOW}Cleaning orphaned graph_runner_edges (if any)...${NC}"
ORPHANED_GRE=$(psql "$PREPROD_URL" -t -c "SELECT COUNT(*) FROM graph_runner_edges WHERE graph_runner_id NOT IN (SELECT DISTINCT id FROM graph_runners)" | tr -d ' ')
if [ "$ORPHANED_GRE" -gt 0 ]; then
    psql "$PREPROD_URL" -c "DELETE FROM graph_runner_edges WHERE graph_runner_id NOT IN (SELECT DISTINCT id FROM graph_runners)" > /dev/null
    echo -e "${GREEN}✓ Deleted $ORPHANED_GRE orphaned graph_runner_edges${NC}"
else
    echo -e "${YELLOW}⚠ No orphaned graph_runner_edges found${NC}"
fi

# Clean up any orphaned graph_runner_nodes (depend on graph_runners)
echo -e "${YELLOW}Cleaning orphaned graph_runner_nodes (if any)...${NC}"
ORPHANED_GRN=$(psql "$PREPROD_URL" -t -c "SELECT COUNT(*) FROM graph_runner_nodes WHERE graph_runner_id NOT IN (SELECT DISTINCT id FROM graph_runners)" | tr -d ' ')
if [ "$ORPHANED_GRN" -gt 0 ]; then
    psql "$PREPROD_URL" -c "DELETE FROM graph_runner_nodes WHERE graph_runner_id NOT IN (SELECT DISTINCT id FROM graph_runners)" > /dev/null
    echo -e "${GREEN}✓ Deleted $ORPHANED_GRN orphaned graph_runner_nodes${NC}"
else
    echo -e "${YELLOW}⚠ No orphaned graph_runner_nodes found${NC}"
fi

# Clean up any orphaned component_instances (depend on graph_runner_nodes)
echo -e "${YELLOW}Cleaning orphaned component_instances (if any)...${NC}"
ORPHANED_CI=$(psql "$PREPROD_URL" -t -c "SELECT COUNT(*) FROM component_instances WHERE id NOT IN (SELECT DISTINCT node_id FROM graph_runner_nodes)" | tr -d ' ')
if [ "$ORPHANED_CI" -gt 0 ]; then
    psql "$PREPROD_URL" -c "DELETE FROM component_instances WHERE id NOT IN (SELECT DISTINCT node_id FROM graph_runner_nodes)" > /dev/null
    echo -e "${GREEN}✓ Deleted $ORPHANED_CI orphaned component_instances${NC}"
else
    echo -e "${YELLOW}⚠ No orphaned component_instances found${NC}"
fi

# Clean up any orphaned graph_runners that weren't caught by the above queries
echo -e "${YELLOW}Cleaning orphaned graph_runners (if any)...${NC}"
ORPHANED_GR=$(psql "$PREPROD_URL" -t -c "SELECT COUNT(*) FROM graph_runners WHERE id NOT IN (SELECT DISTINCT graph_runner_id FROM project_env_binding)" | tr -d ' ')
if [ "$ORPHANED_GR" -gt 0 ]; then
    psql "$PREPROD_URL" -c "DELETE FROM graph_runners WHERE id NOT IN (SELECT DISTINCT graph_runner_id FROM project_env_binding)" > /dev/null
    echo -e "${GREEN}✓ Deleted $ORPHANED_GR orphaned graph_runners${NC}"
else
    echo -e "${YELLOW}⚠ No orphaned graph_runners found${NC}"
fi

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Cleanup Complete!${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "Preprod is now clean and ready for import."
echo ""
echo "Next step: Run 03_import_preprod_data.sh"

