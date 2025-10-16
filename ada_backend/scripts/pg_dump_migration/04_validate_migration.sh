#!/bin/bash
# Validate QA projects migration
#
# This script validates that the migration was successful by checking
# data counts, referential integrity, and polymorphic inheritance.

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
STAGING_URL="${STAGING_DATABASE_URL:-}"
PREPROD_URL="${PREPROD_DATABASE_URL:-}"
ORG_ID="${QA_ORG_ID:-18012b84-b605-4669-95bf-55aa16c5513c}"

# Validate required environment variables
if [ -z "$STAGING_URL" ]; then
    echo -e "${RED}ERROR: STAGING_DATABASE_URL environment variable is not set!${NC}"
    echo ""
    echo "Please set it before running this script:"
    echo "  export STAGING_DATABASE_URL='postgresql://user:pass@host:port/database'"
    exit 1
fi

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
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Migration Validation${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""

# Initialize validation results
VALIDATION_PASSED=true

# Function to run query on both databases and compare
validate_count() {
    local description=$1
    local query=$2
    
    echo -e "${BLUE}Validating: $description${NC}"
    
    local staging_count=$(psql "$STAGING_URL" -t -c "$query" | tr -d ' ')
    local preprod_count=$(psql "$PREPROD_URL" -t -c "$query" | tr -d ' ')
    
    echo "  Staging: $staging_count"
    echo "  Preprod: $preprod_count"
    
    if [ "$staging_count" == "$preprod_count" ]; then
        echo -e "  ${GREEN}✓ PASS${NC}"
    else
        echo -e "  ${RED}✗ FAIL - Counts do not match!${NC}"
        VALIDATION_PASSED=false
    fi
    echo ""
}

# Function to run validation query on preprod
validate_preprod() {
    local description=$1
    local query=$2
    local expected=$3
    
    echo -e "${BLUE}Validating: $description${NC}"
    
    local result=$(psql "$PREPROD_URL" -t -c "$query" | tr -d ' ')
    
    echo "  Result: $result"
    echo "  Expected: $expected"
    
    if [ "$result" == "$expected" ]; then
        echo -e "  ${GREEN}✓ PASS${NC}"
    else
        echo -e "  ${RED}✗ FAIL - Validation failed!${NC}"
        VALIDATION_PASSED=false
    fi
    echo ""
}

echo -e "${GREEN}1. Basic Count Validations${NC}"
echo ""

validate_count "Project count" \
    "SELECT COUNT(*) FROM projects WHERE organization_id = '$ORG_ID'"

validate_count "Workflow projects count" \
    "SELECT COUNT(*) FROM workflow_projects wp 
     JOIN projects p ON wp.id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

validate_count "Agent projects count" \
    "SELECT COUNT(*) FROM agent_projects ap 
     JOIN projects p ON ap.id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

validate_count "Graph runners count" \
    "SELECT COUNT(DISTINCT gr.id) FROM graph_runners gr 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

validate_count "Component instances count" \
    "SELECT COUNT(DISTINCT ci.id) FROM component_instances ci 
     JOIN graph_runner_nodes grn ON ci.id = grn.node_id 
     JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo -e "${GREEN}2. Environment Bindings Validation${NC}"
echo ""

validate_count "Project environment bindings count" \
    "SELECT COUNT(*) FROM project_env_binding peb 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo -e "${GREEN}3. Graph Structure Validation${NC}"
echo ""

validate_count "Graph runner nodes count" \
    "SELECT COUNT(*) FROM graph_runner_nodes grn 
     JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

validate_count "Graph runner edges count" \
    "SELECT COUNT(*) FROM graph_runner_edges gre 
     JOIN graph_runners gr ON gre.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo -e "${GREEN}4. Configuration Data Validation${NC}"
echo ""

validate_count "Basic parameters count" \
    "SELECT COUNT(*) FROM basic_parameters bp 
     JOIN component_instances ci ON bp.component_instance_id = ci.id 
     JOIN graph_runner_nodes grn ON ci.id = grn.node_id 
     JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

validate_count "Port mappings count" \
    "SELECT COUNT(*) FROM port_mappings pm 
     JOIN graph_runners gr ON pm.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

validate_count "Component sub inputs count" \
    "SELECT COUNT(*) FROM component_sub_inputs csi 
     JOIN component_instances ci ON csi.parent_component_instance_id = ci.id 
     JOIN graph_runner_nodes grn ON ci.id = grn.node_id 
     JOIN graph_runners gr ON grn.graph_runner_id = gr.id 
     JOIN project_env_binding peb ON gr.id = peb.graph_runner_id 
     JOIN projects p ON peb.project_id = p.id 
     WHERE p.organization_id = '$ORG_ID'"

echo -e "${GREEN}5. Polymorphic Inheritance Validation${NC}"
echo ""

# Check that all workflow projects have corresponding workflow_projects records
validate_preprod "Workflow projects integrity" \
    "SELECT COUNT(*) FROM projects p 
     LEFT JOIN workflow_projects wp ON p.id = wp.id 
     WHERE p.type = 'workflow' 
     AND p.organization_id = '$ORG_ID' 
     AND wp.id IS NULL" \
    "0"

# Check that all agent projects have corresponding agent_projects records
validate_preprod "Agent projects integrity" \
    "SELECT COUNT(*) FROM projects p 
     LEFT JOIN agent_projects ap ON p.id = ap.id 
     WHERE p.type = 'agent' 
     AND p.organization_id = '$ORG_ID' 
     AND ap.id IS NULL" \
    "0"

echo -e "${GREEN}6. Referential Integrity Validation${NC}"
echo ""

# Check for orphaned workflow_projects
validate_preprod "No orphaned workflow_projects" \
    "SELECT COUNT(*) FROM workflow_projects wp 
     LEFT JOIN projects p ON wp.id = p.id 
     WHERE p.id IS NULL" \
    "0"

# Check for orphaned agent_projects
validate_preprod "No orphaned agent_projects" \
    "SELECT COUNT(*) FROM agent_projects ap 
     LEFT JOIN projects p ON ap.id = p.id 
     WHERE p.id IS NULL" \
    "0"

# Check for bindings without projects
validate_preprod "All bindings have projects" \
    "SELECT COUNT(*) FROM project_env_binding peb 
     LEFT JOIN projects p ON peb.project_id = p.id 
     WHERE p.id IS NULL 
     AND peb.project_id IN (
        SELECT project_id FROM project_env_binding 
        WHERE project_id IN (
            SELECT id FROM projects WHERE organization_id = '$ORG_ID'
        )
     )" \
    "0"

# Check for bindings without graph runners
validate_preprod "All bindings have graph runners" \
    "SELECT COUNT(*) FROM project_env_binding peb 
     LEFT JOIN graph_runners gr ON peb.graph_runner_id = gr.id 
     WHERE gr.id IS NULL 
     AND peb.project_id IN (
        SELECT id FROM projects WHERE organization_id = '$ORG_ID'
     )" \
    "0"

echo ""
echo -e "${GREEN}=====================================${NC}"

if [ "$VALIDATION_PASSED" == true ]; then
    echo -e "${GREEN}✓ ALL VALIDATIONS PASSED${NC}"
    echo -e "${GREEN}=====================================${NC}"
    echo ""
    echo "Migration completed successfully!"
    echo ""
    echo "Next step: Test the API endpoint"
    echo "  curl -X GET 'http://localhost:8000/projects/org/$ORG_ID'"
    exit 0
else
    echo -e "${RED}✗ SOME VALIDATIONS FAILED${NC}"
    echo -e "${RED}=====================================${NC}"
    echo ""
    echo "Please review the failures above and investigate."
    exit 1
fi

