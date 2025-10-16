#!/bin/bash
# Import QA projects data into preprod database
#
# This script imports all exported data from staging into preprod
# in the correct order to maintain referential integrity.

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
PREPROD_URL="${PREPROD_DATABASE_URL:-}"
ORG_ID="${QA_ORG_ID:-18012b84-b605-4669-95bf-55aa16c5513c}"
EXPORT_DIR="./staging_export"

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
echo -e "${GREEN}Import Data to Preprod${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "Organization ID: $ORG_ID"
echo "Import from: $EXPORT_DIR"
echo ""

# Check if export directory exists
if [ ! -d "$EXPORT_DIR" ]; then
    echo -e "${RED}ERROR: Export directory $EXPORT_DIR not found!${NC}"
    echo "Please run 01_export_staging_data.sh first."
    exit 1
fi

# Function to import TSV data
import_table() {
    local table=$1
    local columns=$2
    local tsv_file="$EXPORT_DIR/${table}.tsv"
    
    echo -e "${YELLOW}Importing $table...${NC}"
    
    if [ ! -f "$tsv_file" ]; then
        echo -e "${YELLOW}⚠ File not found: $tsv_file (skipping)${NC}"
        return
    fi
    
    local row_count=$(wc -l < "$tsv_file")
    
    if [ "$row_count" -eq 0 ]; then
        echo -e "${YELLOW}⚠ No data to import for $table${NC}"
        return
    fi
    
    # Import using COPY FROM
    psql "$PREPROD_URL" -c "\COPY $table ($columns) FROM '$tsv_file' WITH (FORMAT text, DELIMITER E'\t')" > /dev/null
    
    echo -e "${GREEN}✓ Imported $row_count rows into $table${NC}"
}

# Function to import with conflict handling (using temp table)
import_table_with_conflict_handling() {
    local table=$1
    local columns=$2
    local tsv_file="$EXPORT_DIR/${table}.tsv"
    
    echo -e "${YELLOW}Importing $table (skipping duplicates)...${NC}"
    
    if [ ! -f "$tsv_file" ]; then
        echo -e "${YELLOW}⚠ File not found: $tsv_file (skipping)${NC}"
        return
    fi
    
    local row_count=$(wc -l < "$tsv_file")
    
    if [ "$row_count" -eq 0 ]; then
        echo -e "${YELLOW}⚠ No data to import for $table${NC}"
        return
    fi
    
    # Create temp table, import, then insert with ON CONFLICT
    psql "$PREPROD_URL" > /dev/null <<EOF
CREATE TEMP TABLE temp_${table} (LIKE ${table} INCLUDING ALL);
\COPY temp_${table} ($columns) FROM '$tsv_file' WITH (FORMAT text, DELIMITER E'\t')
INSERT INTO ${table} SELECT * FROM temp_${table} ON CONFLICT DO NOTHING;
DROP TABLE temp_${table};
EOF
    
    echo -e "${GREEN}✓ Imported $row_count rows into $table (skipped duplicates)${NC}"
}

# Import tables in correct order for referential integrity
echo ""
echo -e "${GREEN}Step 1: Import projects (base table)${NC}"
import_table "projects" "id, name, type, description, organization_id, created_at, updated_at"

echo ""
echo -e "${GREEN}Step 2: Import workflow_projects${NC}"
import_table "workflow_projects" "id"

echo ""
echo -e "${GREEN}Step 3: Import agent_projects${NC}"
import_table "agent_projects" "id"

echo ""
echo -e "${GREEN}Step 4: Import tool_descriptions (referenced by component_instances)${NC}"
import_table_with_conflict_handling "tool_descriptions" "id, name, description, tool_properties, required_tool_properties, created_at, updated_at"

echo ""
echo -e "${GREEN}Step 5: Import component_parameter_definitions (referenced by basic_parameters)${NC}"
import_table_with_conflict_handling "component_parameter_definitions" "id, component_id, name, type, nullable, \"order\", \"default\", ui_component, ui_component_properties, is_advanced"

echo ""
echo -e "${GREEN}Step 6: Import port_definitions (referenced by port_mappings)${NC}"
import_table_with_conflict_handling "port_definitions" "id, component_id, name, port_type"

echo ""
echo -e "${GREEN}Step 7: Import graph_runners${NC}"
import_table "graph_runners" "id, created_at, updated_at, tag_version"

echo ""
echo -e "${GREEN}Step 8: Import component_instances${NC}"
import_table "component_instances" "id, component_id, name, ref, tool_description_id, created_at"

echo ""
echo -e "${GREEN}Step 9: Import project_env_binding${NC}"
import_table "project_env_binding" "id, project_id, environment, graph_runner_id, created_at, updated_at"

echo ""
echo -e "${GREEN}Step 10: Import graph_runner_nodes${NC}"
import_table "graph_runner_nodes" "id, node_id, graph_runner_id, node_type, is_start_node, created_at, updated_at"

echo ""
echo -e "${GREEN}Step 11: Import graph_runner_edges${NC}"
import_table "graph_runner_edges" "id, source_node_id, target_node_id, graph_runner_id, \"order\", created_at, updated_at"

echo ""
echo -e "${GREEN}Step 12: Import basic_parameters${NC}"
import_table "basic_parameters" "id, component_instance_id, parameter_definition_id, value, organization_secret_id, \"order\""

echo ""
echo -e "${GREEN}Step 13: Import port_mappings${NC}"
import_table "port_mappings" "id, graph_runner_id, source_instance_id, source_port_definition_id, target_instance_id, target_port_definition_id, dispatch_strategy"

echo ""
echo -e "${GREEN}Step 14: Import component_sub_inputs${NC}"
import_table "component_sub_inputs" "id, parent_component_instance_id, child_component_instance_id, parameter_definition_id, \"order\""

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Import Complete!${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "Next step: Run 04_validate_migration.sh to verify the migration"

