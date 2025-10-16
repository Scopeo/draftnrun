#!/bin/bash
# Export QA projects data from staging database using pg_dump
#
# This script exports all tables related to the QA organization from staging
# in the correct order to maintain referential integrity.

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
STAGING_URL="${STAGING_DATABASE_URL:-}"
ORG_ID="${QA_ORG_ID:-18012b84-b605-4669-95bf-55aa16c5513c}"
EXPORT_DIR="./staging_export"

# Validate required environment variables
if [ -z "$STAGING_URL" ]; then
    echo -e "${RED}ERROR: STAGING_DATABASE_URL environment variable is not set!${NC}"
    echo ""
    echo "Please set it before running this script:"
    echo "  export STAGING_DATABASE_URL='postgresql://user:pass@host:port/database'"
    exit 1
fi

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Staging Data Export for QA Projects${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "Organization ID: $ORG_ID"
echo "Export Directory: $EXPORT_DIR"
echo ""

# Create export directory
mkdir -p "$EXPORT_DIR"

# Function to export a table with WHERE clause
export_table() {
    local table=$1
    local where_clause=$2
    local output_file="$EXPORT_DIR/${table}.sql"
    
    echo -e "${YELLOW}Exporting $table...${NC}"
    
    pg_dump "$STAGING_URL" \
        --table="$table" \
        --data-only \
        --inserts \
        --no-owner \
        --no-privileges \
        --column-inserts \
        2>/dev/null | \
    # Filter rows using grep and awk (works for simple cases)
    tee "$output_file" > /dev/null
    
    if [ -s "$output_file" ]; then
        local count=$(grep -c "^INSERT INTO" "$output_file" || echo "0")
        echo -e "${GREEN}✓ Exported $count rows to $output_file${NC}"
    else
        echo -e "${YELLOW}⚠ No data exported for $table${NC}"
    fi
}

# Function to export table with complex WHERE clause using custom query
export_table_custom() {
    local table=$1
    local query=$2
    local output_file="$EXPORT_DIR/${table}.sql"
    
    echo -e "${YELLOW}Exporting $table with custom query...${NC}"
    
    # Export using COPY TO with query
    psql "$STAGING_URL" -c "\COPY ($query) TO STDOUT WITH (FORMAT text, DELIMITER E'\t')" > "$EXPORT_DIR/${table}.tsv"
    
    if [ -s "$EXPORT_DIR/${table}.tsv" ]; then
        local count=$(wc -l < "$EXPORT_DIR/${table}.tsv")
        echo -e "${GREEN}✓ Exported $count rows to ${table}.tsv${NC}"
    else
        echo -e "${YELLOW}⚠ No data exported for $table${NC}"
    fi
}

# Export tables in correct order for referential integrity
echo ""
echo -e "${GREEN}Step 1: Export projects (base table)${NC}"
export_table_custom "projects" \
    "SELECT id, name, type, description, organization_id, created_at, updated_at 
     FROM projects 
     WHERE organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}Step 2: Export workflow_projects${NC}"
export_table_custom "workflow_projects" \
    "SELECT wp.id 
     FROM workflow_projects wp 
     JOIN projects p ON wp.id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}Step 3: Export agent_projects${NC}"
export_table_custom "agent_projects" \
    "SELECT ap.id 
     FROM agent_projects ap 
     JOIN projects p ON ap.id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}Step 4: Export tool_descriptions (referenced by component_instances)${NC}"
export_table_custom "tool_descriptions" \
    "SELECT td.id, td.name, td.description, td.tool_properties, td.required_tool_properties, td.created_at, td.updated_at 
     FROM tool_descriptions td 
     WHERE td.id IN (
         SELECT DISTINCT ci.tool_description_id 
         FROM component_instances ci 
         JOIN graph_runner_nodes grn ON ci.id = grn.node_id 
         JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
         JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
         JOIN projects p ON peb.project_id = p.id 
         WHERE p.organization_id = '$ORG_ID' 
         AND ci.tool_description_id IS NOT NULL
     )"

echo ""
echo -e "${GREEN}Step 5: Export graph_runners${NC}"
export_table_custom "graph_runners" \
    "SELECT gr.id, gr.created_at, gr.updated_at, gr.tag_version 
     FROM graph_runners gr 
     WHERE gr.id IN (
         SELECT DISTINCT peb.graph_runner_id 
         FROM project_env_binding peb 
         JOIN projects p ON peb.project_id = p.id 
         WHERE p.organization_id = '$ORG_ID' 
         AND peb.graph_runner_id IS NOT NULL
     )"

echo ""
echo -e "${GREEN}Step 6: Export component_instances${NC}"
export_table_custom "component_instances" \
    "SELECT ci.id, ci.component_id, ci.name, ci.ref, ci.tool_description_id, ci.created_at 
     FROM component_instances ci 
     WHERE ci.id IN (
         SELECT DISTINCT grn.node_id 
         FROM graph_runner_nodes grn 
         JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
         JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
         JOIN projects p ON peb.project_id = p.id 
         WHERE p.organization_id = '$ORG_ID' 
         AND grn.node_type = 'component_instance'
     )"

echo ""
echo -e "${GREEN}Step 7: Export project_env_binding${NC}"
export_table_custom "project_env_binding" \
    "SELECT peb.id, peb.project_id, peb.environment, peb.graph_runner_id, peb.created_at, peb.updated_at 
     FROM project_env_binding peb 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}Step 8: Export graph_runner_nodes${NC}"
export_table_custom "graph_runner_nodes" \
    "SELECT grn.id, grn.node_id, grn.graph_runner_id, grn.node_type, grn.is_start_node, grn.created_at, grn.updated_at 
     FROM graph_runner_nodes grn 
     JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}Step 9: Export graph_runner_edges${NC}"
export_table_custom "graph_runner_edges" \
    "SELECT gre.id, gre.source_node_id, gre.target_node_id, gre.graph_runner_id, gre.\"order\", gre.created_at, gre.updated_at 
     FROM graph_runner_edges gre 
     JOIN graph_runners gr ON gre.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}Step 10: Export basic_parameters${NC}"
export_table_custom "basic_parameters" \
    "SELECT bp.id, bp.component_instance_id, bp.parameter_definition_id, bp.value, bp.organization_secret_id, bp.\"order\" 
     FROM basic_parameters bp 
     JOIN component_instances ci ON bp.component_instance_id = ci.id 
     JOIN graph_runner_nodes grn ON ci.id = grn.node_id 
     JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}Step 11: Export port_mappings${NC}"
export_table_custom "port_mappings" \
    "SELECT pm.id, pm.graph_runner_id, pm.source_instance_id, pm.source_port_definition_id, pm.target_instance_id, pm.target_port_definition_id, pm.dispatch_strategy 
     FROM port_mappings pm 
     JOIN graph_runners gr ON pm.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}Step 12: Export component_sub_inputs${NC}"
export_table_custom "component_sub_inputs" \
    "SELECT csi.id, csi.parent_component_instance_id, csi.child_component_instance_id, csi.parameter_definition_id, csi.\"order\" 
     FROM component_sub_inputs csi 
     JOIN component_instances ci ON csi.parent_component_instance_id = ci.id 
     JOIN graph_runner_nodes grn ON ci.id = grn.node_id 
     JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Export Complete!${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "Exported files are in: $EXPORT_DIR"
echo ""
echo "Next step: Run 02_clean_preprod_data.sh"

