#!/usr/bin/env python3
"""
Environment validation script for QA migration.

Validates that the required environment variables are set and database connections work.
Does not contain any sensitive data - requires environment variables to be set externally.
"""

import os
import sys
from migration_db_connection import DatabaseConnectionManager


def validate_environment():
    """Validate the migration environment."""
    print("Validating QA migration environment...")

    # Check environment variables
    staging_url = os.getenv("STAGING_DATABASE_URL")
    preprod_url = os.getenv("PREPROD_DATABASE_URL")

    if not staging_url:
        print("❌ STAGING_DATABASE_URL environment variable not set")
        return False

    if not preprod_url:
        print("❌ PREPROD_DATABASE_URL environment variable not set")
        return False

    print("✅ Environment variables found")

    try:
        db_manager = DatabaseConnectionManager()

        # Test connections
        results = db_manager.validate_connections()

        if results["staging"]:
            print("✅ Staging database connection: OK")
        else:
            print("❌ Staging database connection: FAILED")
            return False

        if results["preprod"]:
            print("✅ Preprod database connection: OK")
        else:
            print("❌ Preprod database connection: FAILED")
            return False

        # Test staging data access
        try:
            staging_data = db_manager.execute_staging_query(
                "SELECT COUNT(*) as count FROM projects WHERE organization_id = %s",
                ("18012b84-b605-4669-95bf-55aa16c5513c",),
            )
            project_count = staging_data[0]["count"]
            print(f"✅ Staging data access: OK ({project_count} projects found)")
        except Exception as e:
            print(f"❌ Staging data access: FAILED - {e}")
            return False

        # Test preprod data access
        try:
            preprod_data = db_manager.execute_preprod_query(
                "SELECT COUNT(*) as count FROM projects WHERE organization_id = %s",
                ("18012b84-b605-4669-95bf-55aa16c5513c",),
            )
            project_count = preprod_data[0]["count"]
            print(f"✅ Preprod data access: OK ({project_count} projects found)")
        except Exception as e:
            print(f"❌ Preprod data access: FAILED - {e}")
            return False

        db_manager.close_all_connections()
        print("\n✅ Environment validation successful")
        return True

    except Exception as e:
        print(f"❌ Environment validation failed: {e}")
        return False


def main():
    """Main validation function."""
    if not validate_environment():
        print("\n❌ Environment validation failed")
        print("Please check your environment variables and database connections")
        sys.exit(1)

    print("\n✅ Environment validation complete - ready for migration")
    print("\nNext steps:")
    print("1. Run dry-run: python migrate_qa_projects_sql.py --dry-run")
    print("2. Execute migration: python migrate_qa_projects_sql.py")
    print("3. Rollback if needed: python migrate_qa_projects_sql.py --rollback")


if __name__ == "__main__":
    main()
