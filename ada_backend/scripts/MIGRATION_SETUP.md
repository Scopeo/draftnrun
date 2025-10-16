# QA Migration Setup Guide

## Environment Variables Required

Before running the migration, you must set the following environment variables:

```bash
export STAGING_DATABASE_URL="postgresql://user:password@host:port/database"
export PREPROD_DATABASE_URL="postgresql://user:password@host:port/database"
```

## Migration Scripts

### 1. Main Migration Script

```bash
python migrate_qa_projects_sql.py
```

Options:

- `--dry-run`: Show what would be migrated without executing
- `--rollback`: Rollback migration by cleaning QA org data

### 2. Cleanup Script

```bash
python cleanup_qa_preprod.py
```

Options:

- `--dry-run`: Show what would be deleted without executing
- `--verify-only`: Only verify current state without cleanup

## Migration Process

1. **Setup Environment**: Set the required database URLs
2. **Dry Run**: Test the migration without executing: `python migrate_qa_projects_sql.py --dry-run`
3. **Execute Migration**: Run the actual migration: `python migrate_qa_projects_sql.py`
4. **Verify Results**: Check that all projects are accessible in the UI
5. **Rollback if Needed**: `python migrate_qa_projects_sql.py --rollback`

## Safety Features

- **Read-only staging**: All staging connections are read-only
- **Transaction safety**: Each step runs in a transaction
- **Validation gates**: Migration stops if validation fails
- **Comprehensive logging**: All operations are logged
- **Simple rollback**: Single command to clean QA org data

## Target Organization

- **Organization ID**: `18012b84-b605-4669-95bf-55aa16c5513c`
- **Migration Method**: Direct SQL with preserved UUIDs
- **Validation**: Comprehensive checks at each step
