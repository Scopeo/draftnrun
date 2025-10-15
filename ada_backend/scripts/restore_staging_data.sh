#!/bin/bash
# restore_staging_data.sh - Restore staging data to local database

set -e  # Exit on any error

# Check if required arguments are provided
if [ $# -ne 2 ]; then
    echo "Usage: $0 <db_url> <backup_path>"
    echo "Example: $0 'postgresql://postgres:ada_password@localhost:5432/ada_backend' './staging_backup'"
    exit 1
fi

DB_URL="$1"
BACKUP_PATH="$2"

# Check if backup directory exists
if [ ! -d "$BACKUP_PATH" ]; then
    echo "❌ Error: Backup directory does not exist: $BACKUP_PATH"
    exit 1
fi

echo "🔄 Restoring staging data from: $BACKUP_PATH"
echo "🔗 Database: $DB_URL"

# Restore in dependency order
echo "🔄 Restoring component definitions..."
if [ -f "$BACKUP_PATH/components.sql" ]; then
    psql "$DB_URL" -f "$BACKUP_PATH/components.sql"
else
    echo "⚠️  Warning: components.sql not found"
fi

echo "🔄 Restoring integration data..."
if [ -f "$BACKUP_PATH/integrations.sql" ]; then
    psql "$DB_URL" -f "$BACKUP_PATH/integrations.sql"
else
    echo "⚠️  Warning: integrations.sql not found"
fi

echo "🔄 Restoring tool descriptions..."
if [ -f "$BACKUP_PATH/tool_descriptions.sql" ]; then
    psql "$DB_URL" -f "$BACKUP_PATH/tool_descriptions.sql"
else
    echo "⚠️  Warning: tool_descriptions.sql not found"
fi

echo "🔄 Restoring organization data..."
if [ -f "$BACKUP_PATH/organization_data.sql" ]; then
    psql "$DB_URL" -f "$BACKUP_PATH/organization_data.sql"
else
    echo "⚠️  Warning: organization_data.sql not found"
fi

echo "🔄 Restoring project data..."
if [ -f "$BACKUP_PATH/project_data.sql" ]; then
    psql "$DB_URL" -f "$BACKUP_PATH/project_data.sql"
else
    echo "⚠️  Warning: project_data.sql not found"
fi

echo "🔄 Restoring quality assurance data..."
if [ -f "$BACKUP_PATH/qa_data.sql" ]; then
    psql "$DB_URL" -f "$BACKUP_PATH/qa_data.sql"
else
    echo "⚠️  Warning: qa_data.sql not found"
fi


echo "🔄 Restoring data sources..."
if [ -f "$BACKUP_PATH/data_sources.sql" ]; then
    psql "$DB_URL" -f "$BACKUP_PATH/data_sources.sql"
else
    echo "⚠️  Warning: data_sources.sql not found"
fi

echo "✅ Restore completed successfully!"
echo "🎉 QA projects should now be available in your local database"
