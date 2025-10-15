#!/bin/bash
# backup_staging_data.sh - Backup all essential data from staging for QA projects

set -e  # Exit on any error

# Check if required arguments are provided
if [ $# -ne 2 ]; then
    echo "Usage: $0 <db_url> <output_path>"
    echo "Example: $0 'postgresql://user:pass@host:5432/db' './staging_backup'"
    exit 1
fi

DB_URL="$1"
OUTPUT_PATH="$2"

# Create output directory
mkdir -p "$OUTPUT_PATH"

echo "📦 Backing up staging data to: $OUTPUT_PATH"
echo "🔗 Database: $DB_URL"

# Backup all essential tables for QA projects
echo "📦 Backing up component definitions..."
pg_dump "$DB_URL" \
  --table=components \
  --table=component_parameter_definitions \
  --table=component_global_parameters \
  --table=port_definitions \
  --data-only \
  --file="$OUTPUT_PATH/components.sql"

echo "📦 Backing up integration data..."
pg_dump "$DB_URL" \
  --table=integrations \
  --table=secret_integrations \
  --table=integration_component_instance_relationships \
  --data-only \
  --file="$OUTPUT_PATH/integrations.sql"

echo "📦 Backing up tool descriptions..."
pg_dump "$DB_URL" \
  --table=tool_descriptions \
  --data-only \
  --file="$OUTPUT_PATH/tool_descriptions.sql"

echo "📦 Backing up organization data..."
pg_dump "$DB_URL" \
  --table=organization_secrets \
  --table=categories \
  --table=component_categories \
  --data-only \
  --file="$OUTPUT_PATH/organization_data.sql"

echo "📦 Backing up project data..."
pg_dump "$DB_URL" \
  --table=projects \
  --table=workflow_projects \
  --table=agent_projects \
  --table=project_env_binding \
  --table=graph_runners \
  --table=component_instances \
  --table=graph_runner_edges \
  --table=graph_runner_nodes \
  --table=basic_parameters \
  --table=component_sub_inputs \
  --data-only \
  --file="$OUTPUT_PATH/project_data.sql"

echo "📦 Backing up quality assurance data..."
pg_dump "$DB_URL" \
  --table=quality_assurance.input_groundtruth \
  --table=quality_assurance.dataset_project \
  --table=quality_assurance.version_output \
  --data-only \
  --file="$OUTPUT_PATH/qa_data.sql"

echo "📦 Backing up data sources..."
pg_dump "$DB_URL" \
  --table=data_sources \
  --table=source_attributes \
  --table=ingestion_tasks \
  --data-only \
  --file="$OUTPUT_PATH/data_sources.sql"

echo "✅ Backup completed successfully!"
echo "📁 Files created in: $OUTPUT_PATH"
ls -la "$OUTPUT_PATH"
