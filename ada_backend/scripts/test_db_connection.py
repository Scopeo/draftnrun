#!/usr/bin/env python
"""
Simple script to test database connection.
Run with: python -m ada_backend.scripts.test_db_connection
"""

import sys

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from ada_backend.database.setup_db import engine, get_db_url
from settings import settings


def test_connection():
    """Test database connection and print info about the connection."""
    print("\n=== Database Connection Test ===\n")

    # Get configured database URL (with password masked)
    try:
        db_url = get_db_url()
        masked_url = db_url.replace(settings.ADA_DB_PASSWORD or "", "******") if settings.ADA_DB_PASSWORD else db_url
        print(f"Database URL: {masked_url}")
        print(f"Database Type: {settings.ADA_DB_DRIVER or 'sqlite'}")
    except Exception as e:
        print(f"ERROR: Failed to get database URL: {str(e)}")
        return False

    # Test actual connection
    try:
        # Try to connect and execute a simple query
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            result.fetchone()

        print("Connection: SUCCESS ✅")

        # Get database info
        inspector = inspect(engine)

        # Print tables if any exist
        tables = inspector.get_table_names()
        if tables:
            print(f"\nDatabase tables ({len(tables)}):")
            for table in sorted(tables):
                print(f"  - {table}")
        else:
            print("\nNo tables found in database. Run setup_db.py to create tables.")

        # Print database-specific info
        if settings.ADA_DB_DRIVER == "postgresql":
            print(f"\nPostgreSQL Database: {settings.ADA_DB_NAME}")
            print(f"Host: {settings.ADA_DB_HOST}:{settings.ADA_DB_PORT}")
            print(f"User: {settings.ADA_DB_USER}")
        else:
            sqlite_path = settings.ADA_DB_URL.replace("sqlite:///", "") if settings.ADA_DB_URL else "unknown"
            print("\nSQLite Database:", sqlite_path)

        return True

    except SQLAlchemyError as e:
        print("Connection: FAILED ❌")
        print(f"Error: {str(e)}")
        return False


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
