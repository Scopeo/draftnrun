"""PostgreSQL Database Copy Utility

This script provides functionality to copy/clone a PostgreSQL database from one location to another.
It uses pg_dump and psql commands to perform the operation.

Requirements:
    - PostgreSQL client tools installed (pg_dump and psql)
    - Access to both source and destination databases
    - Sufficient disk space for temporary dump file

Usage:
    python pg_copy.py <source_db_url> <dest_db_url>

    source_db_url: PostgreSQL connection URL for source database
                   Format: postgresql://[user[:password]@][host][:port][/dbname]
    dest_db_url:   PostgreSQL connection URL for destination database
                   Format: postgresql://[user[:password]@][host][:port][/dbname]

Example:
    python pg_copy.py postgresql://postgres:postgres@localhost:5432/ada_backend \\
                      postgresql://postgres:postgres@localhost:5432/ada_backend_test

Note:
    - The script will create a temporary SQL dump file
    - The destination database will be dropped and recreated if it exists
    - Connection URLs are masked in logs for security
"""

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional


def check_command_exists(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise EnvironmentError(f"Required command '{cmd}' not found in PATH.")


def run_command(cmd: list[str], env: Optional[dict[str, str]] = None) -> None:
    masked_cmd = [part if "://" not in part else "<connection_url>" for part in cmd]
    print(f"Running: {' '.join(masked_cmd)}")
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with return code {result.returncode}")


def copy_database(source_url: str, dest_url: str) -> None:
    check_command_exists("pg_dump")
    check_command_exists("psql")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".sql") as tmp:
        dump_path = tmp.name

    try:
        print("📤 Step 1: Dumping source database...")
        run_command([
            "pg_dump",
            "--clean",
            "--create",
            "--dbname",
            source_url,
            "-f",
            dump_path,
            "--no-owner",
            "--no-privileges",
        ])

        print("📥 Step 2: Restoring into destination database...")
        run_command(["psql", dest_url, "-f", dump_path])

        print("✅ Database clone completed successfully.")
    finally:
        if os.path.exists(dump_path):
            os.remove(dump_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python pg_clone.py <source_db_url> <dest_db_url>")
        sys.exit(1)

    source_db = sys.argv[1]
    dest_db = sys.argv[2]

    try:
        copy_database(source_db, dest_db)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(2)
