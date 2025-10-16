# QA Projects Migration - pg_dump/psql Approach

Simple, reliable migration scripts using PostgreSQL native tools instead of complex Python code.

## Overview

This migration approach uses `pg_dump` and `psql` to copy QA organization projects from staging to preprod. It's much simpler and more reliable than the Python-based approach.

## Files

- **`01_export_staging_data.sh`** - Export data from staging to TSV files
- **`02_clean_preprod_data.sh`** - Clean existing QA data from preprod
- **`03_import_preprod_data.sh`** - Import TSV files into preprod
- **`04_validate_migration.sh`** - Validate the migration was successful
- **`migrate_qa_projects.sh`** - Master script that runs all steps

## Prerequisites

1. **PostgreSQL client tools** (`psql` and `pg_dump`)
2. **Database connection strings** (as environment variables)
3. **SSH access** to preprod server

## Setup on Preprod Server

### 1. SSH to Preprod

```bash
ssh ada-preprod
cd /home/ec2-user/draftnrun
```

### 2. Pull Latest Code

```bash
git pull origin pablo/dra-558-setup-preprod-with-production-data-for-exceptional-qa
```

### 3. Set Environment Variables

You need to set these environment variables before running the migration:

```bash
# Staging database (source)
export STAGING_DATABASE_URL='postgresql://user:pass@staging-host:5432/ada_backend'

# Preprod database (target)
export PREPROD_DATABASE_URL='postgresql://user:pass@preprod-host:5432/ada_backend'

# Optional: Override organization ID (default is QA org)
export QA_ORG_ID='18012b84-b605-4669-95bf-55aa16c5513c'
```

**Where to get credentials:**

- Check `credentials.env` on the server
- Or get from Pulumi config (see below)

### 4. Get Credentials from Pulumi (if needed)

```bash
cd /path/to/ada-infra

# Staging credentials
pulumi config get ada-infra:db_username --stack staging
pulumi config get ada-infra:db_password --stack staging
pulumi stack output db_endpoint --stack staging

# Preprod credentials
pulumi config get ada-infra:db_username --stack preprod
pulumi config get ada-infra:db_password --stack preprod
pulumi stack output db_endpoint --stack preprod
```

## Usage

### Option 1: Run Complete Migration (Recommended)

Run the master script that executes all steps:

```bash
cd /home/ec2-user/draftnrun/ada_backend/scripts/pg_dump_migration
chmod +x *.sh
./migrate_qa_projects.sh
```

This will:

1. Check prerequisites
2. Show migration info and ask for confirmation
3. Export data from staging
4. Clean preprod data
5. Import data to preprod
6. Validate the migration

### Option 2: Run Individual Steps

Run each script separately if you need more control:

```bash
cd /home/ec2-user/draftnrun/ada_backend/scripts/pg_dump_migration

# Make scripts executable
chmod +x *.sh

# Step 1: Export data from staging
./01_export_staging_data.sh

# Step 2: Clean preprod (will ask for confirmation)
./02_clean_preprod_data.sh

# Step 3: Import to preprod
./03_import_preprod_data.sh

# Step 4: Validate migration
./04_validate_migration.sh
```

## What Gets Migrated

The migration copies all data for the QA organization (`18012b84-b605-4669-95bf-55aa16c5513c`):

### Core Tables

- **projects** - Base project records
- **workflow_projects** - Workflow project polymorphic records
- **agent_projects** - Agent project polymorphic records

### Graph Data

- **graph_runners** - Graph runner instances
- **component_instances** - Component instances
- **project_env_binding** - Environment bindings (draft/production)

### Graph Structure

- **graph_runner_nodes** - Nodes in the graph
- **graph_runner_edges** - Connections between nodes

### Configuration

- **basic_parameters** - Component parameters
- **port_mappings** - Data flow between components
- **component_sub_inputs** - Component dependencies

## Migration Order

The scripts handle tables in the correct order to maintain referential integrity:

1. Projects (base table)
2. Polymorphic tables (workflow_projects, agent_projects)
3. Graph runners
4. Component instances
5. Environment bindings
6. Graph structure (nodes, edges)
7. Configuration (parameters, mappings)

## Validation

The validation script checks:

✅ **Data counts match** between staging and preprod  
✅ **Polymorphic inheritance** is correct  
✅ **Environment bindings** exist for all projects  
✅ **Graph structure** is complete  
✅ **Referential integrity** is maintained  
✅ **No orphaned records**

## Rollback

If something goes wrong, you can rollback by running the cleanup script:

```bash
./02_clean_preprod_data.sh
```

This deletes all QA organization data from preprod, returning it to a clean state.

## Testing After Migration

### 1. Test the API Endpoint

```bash
# From preprod server (or with SSH tunnel)
curl -X GET 'http://localhost:8000/projects/org/18012b84-b605-4669-95bf-55aa16c5513c'
```

Expected: Should return all 14 projects with full details

### 2. Check in the UI

Navigate to the preprod URL and verify:

- All projects are visible
- Components are displayed correctly
- Projects can be opened and edited

## Troubleshooting

### "psql: command not found"

Install PostgreSQL client tools:

```bash
sudo yum install postgresql  # Amazon Linux
```

### "Cannot connect to database"

Check:

1. Environment variables are set correctly
2. Database credentials are correct
3. Network access from preprod to staging/preprod databases

### "Permission denied" when running scripts

Make scripts executable:

```bash
chmod +x *.sh
```

### Validation failures

Check the validation output for specific issues:

- Count mismatches → Re-run export/import steps
- Orphaned records → Check referential integrity
- Missing polymorphic records → Check database schema

## Advantages Over Python Approach

✅ **Much simpler** - Standard PostgreSQL tools  
✅ **More reliable** - Battle-tested utilities  
✅ **Easier to debug** - Plain SQL and shell scripts  
✅ **Handles data types automatically** - No manual type conversion  
✅ **Preserves relationships** - Referential integrity maintained  
✅ **Fast** - Native PostgreSQL operations  
✅ **Easy to understand** - No complex Python code

## Files Created During Migration

- `staging_export/*.tsv` - Exported data from staging (can be deleted after migration)

These files are automatically created in the script directory and can be cleaned up after successful migration.

## Security Notes

- **No credentials in code** - All connection strings come from environment variables
- **Safe for git** - Scripts can be committed without exposing secrets
- **Confirmation required** - Cleanup script asks for confirmation before deleting data

## Support

If you encounter issues:

1. Check the validation output for specific errors
2. Review the migration log files
3. Verify environment variables are set correctly
4. Check database connectivity

For more details, see the comprehensive migration report:

- `/path/to/.cursor/wips/preprod_backup/AA-comprehensive-migration-report.md`
