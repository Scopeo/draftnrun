#!/bin/bash
# Master migration orchestration script
#
# This script orchestrates the complete QA projects migration from staging to preprod
# using the pg_dump/psql approach.

set -e  # Exit on error
set -u  # Exit on undefined variable

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ORG_ID="${QA_ORG_ID:-18012b84-b605-4669-95bf-55aa16c5513c}"
STAGING_URL="${STAGING_DATABASE_URL:-}"
PREPROD_URL="${PREPROD_DATABASE_URL:-}"

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

# Function to print banner
print_banner() {
    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
    echo ""
}

# Function to print step
print_step() {
    echo ""
    echo -e "${GREEN}>>> $1${NC}"
    echo ""
}

# Function to check prerequisites
check_prerequisites() {
    print_step "Checking prerequisites..."
    
    # Check if psql is installed
    if ! command -v psql &> /dev/null; then
        echo -e "${RED}ERROR: psql is not installed!${NC}"
        echo "Please install PostgreSQL client tools."
        exit 1
    fi
    
    # Check if pg_dump is installed
    if ! command -v pg_dump &> /dev/null; then
        echo -e "${RED}ERROR: pg_dump is not installed!${NC}"
        echo "Please install PostgreSQL client tools."
        exit 1
    fi
    
    # Check database connections
    echo "Testing staging database connection..."
    if ! psql "$STAGING_URL" -c "SELECT 1" > /dev/null 2>&1; then
        echo -e "${RED}ERROR: Cannot connect to staging database!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Staging database connection OK${NC}"
    
    echo "Testing preprod database connection..."
    if ! psql "$PREPROD_URL" -c "SELECT 1" > /dev/null 2>&1; then
        echo -e "${RED}ERROR: Cannot connect to preprod database!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Preprod database connection OK${NC}"
    
    echo ""
    echo -e "${GREEN}✓ All prerequisites met${NC}"
}

# Function to show migration info
show_migration_info() {
    print_banner "QA Projects Migration - Staging to Preprod"
    
    echo "Organization ID: $ORG_ID"
    echo ""
    echo "Source: Staging Database"
    echo "Target: Preprod Database"
    echo ""
    echo "Migration Method: pg_dump + psql (TSV format)"
    echo ""
    echo -e "${YELLOW}This migration will:${NC}"
    echo "  1. Export data from staging database"
    echo "  2. Clean existing data from preprod database"
    echo "  3. Import data into preprod database"
    echo "  4. Validate the migration"
    echo ""
    echo -e "${RED}WARNING: This will DELETE all QA organization data from preprod!${NC}"
    echo ""
}

# Function to confirm migration
confirm_migration() {
    echo -e "${YELLOW}Do you want to proceed with the migration? (yes/no): ${NC}"
    read -r response
    
    if [ "$response" != "yes" ]; then
        echo ""
        echo "Migration cancelled."
        exit 0
    fi
}

# Main execution
main() {
    # Show migration info
    show_migration_info
    
    # Check prerequisites
    check_prerequisites
    
    # Confirm migration
    confirm_migration
    
    # Start migration
    print_banner "Starting Migration"
    
    MIGRATION_START_TIME=$(date +%s)
    
    # Step 1: Export staging data
    print_step "Step 1/4: Exporting data from staging..."
    bash "$SCRIPT_DIR/01_export_staging_data.sh"
    
    # Step 2: Clean preprod data
    print_step "Step 2/4: Cleaning preprod data..."
    # Pass 'yes' automatically to the cleanup script
    echo "yes" | bash "$SCRIPT_DIR/02_clean_preprod_data.sh"
    
    # Step 3: Import to preprod
    print_step "Step 3/4: Importing data to preprod..."
    bash "$SCRIPT_DIR/03_import_preprod_data.sh"
    
    # Step 4: Validate migration
    print_step "Step 4/4: Validating migration..."
    bash "$SCRIPT_DIR/04_validate_migration.sh"
    
    # Calculate migration time
    MIGRATION_END_TIME=$(date +%s)
    MIGRATION_DURATION=$((MIGRATION_END_TIME - MIGRATION_START_TIME))
    
    # Success banner
    print_banner "Migration Completed Successfully!"
    
    echo "Migration completed in $MIGRATION_DURATION seconds"
    echo ""
    echo -e "${GREEN}✓ All steps completed successfully${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Test the API endpoint:"
    echo "     curl -X GET 'http://localhost:8000/projects/org/$ORG_ID'"
    echo ""
    echo "  2. Check the UI to ensure projects are visible with components"
    echo ""
}

# Handle script interruption
trap 'echo ""; echo -e "${RED}Migration interrupted by user${NC}"; exit 1' INT

# Run main function
main

