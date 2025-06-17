#!/usr/bin/env python3
import argparse
import csv
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras


def load_csv_to_table(conn, csv_path, table_name, disable_triggers=False):
    cursor = conn.cursor()

    if disable_triggers:
        cursor.execute(f"ALTER TABLE {table_name} DISABLE TRIGGER ALL;")

    # Get columns from CSV header
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        columns = next(reader)

    # Check schema for not-null columns to handle properly
    not_null_columns = get_not_null_columns(conn, table_name)
    not_null_indices = [i for i, col in enumerate(columns) if col in not_null_columns]

    # Build INSERT statement
    placeholders = ",".join(["%s"] * len(columns))
    columns_str = ",".join(f'"{col}"' for col in columns)  # Quote column names to handle reserved keywords
    insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

    # Read and insert data
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        next(reader)  # Skip header

        batch = []
        batch_size = 1000
        row_count = 0

        for row in reader:
            # Convert empty strings to None for most columns, but to empty string for not-null text columns
            cleaned_row = []
            for i, val in enumerate(row):
                if val == "":
                    if i in not_null_indices:
                        # For not-null columns, use empty string instead of null
                        cleaned_row.append("")
                    else:
                        # For nullable columns, use null
                        cleaned_row.append(None)
                else:
                    cleaned_row.append(val)

            batch.append(cleaned_row)
            row_count += 1

            if len(batch) >= batch_size:
                cursor.executemany(insert_query, batch)
                batch = []

        if batch:
            cursor.executemany(insert_query, batch)

    if disable_triggers:
        cursor.execute(f"ALTER TABLE {table_name} ENABLE TRIGGER ALL;")

    conn.commit()
    return row_count


def get_not_null_columns(conn, table_name):
    """Get list of column names that are defined as NOT NULL in the database."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND is_nullable = 'NO' AND column_default IS NULL
        """,
        (table_name,),
    )
    return [row[0] for row in cursor.fetchall()]


def clear_tables(conn, tables):
    """Clear all specified tables in reverse order to respect foreign key constraints."""
    cursor = conn.cursor()
    print("Clearing existing tables...")

    # Disable triggers to avoid foreign key constraint issues
    cursor.execute("SET session_replication_role = 'replica';")

    # Truncate tables in reverse order
    for table_name in reversed(tables):
        try:
            cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE;")
            print(f"  Cleared table '{table_name}'")
        except Exception as e:
            print(f"  Error clearing table '{table_name}': {e}")

    # Re-enable triggers
    cursor.execute("SET session_replication_role = 'origin';")
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Load CSV files into PostgreSQL")
    parser.add_argument("--csv_dir", type=str, required=True, help="Directory containing CSV files")
    parser.add_argument("--pg_host", type=str, default="localhost", help="PostgreSQL host")
    parser.add_argument("--pg_port", type=str, default="5432", help="PostgreSQL port")
    parser.add_argument("--pg_dbname", type=str, required=True, help="PostgreSQL database name")
    parser.add_argument("--pg_user", type=str, required=True, help="PostgreSQL username")
    parser.add_argument("--pg_password", type=str, required=True, help="PostgreSQL password")
    parser.add_argument("--disable_triggers", action="store_true", help="Disable triggers during import")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before import")

    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)

    # Check if CSV directory exists
    if not csv_dir.exists() or not csv_dir.is_dir():
        print(f"Error: CSV directory '{csv_dir}' not found or is not a directory.", file=sys.stderr)
        return 1

    # Connect to PostgreSQL
    try:
        connection_string = (
            f"host={args.pg_host} port={args.pg_port} dbname={args.pg_dbname} "
            f"user={args.pg_user} password={args.pg_password}"
        )
        conn = psycopg2.connect(connection_string)

        # Enable psycopg2 to handle UUIDs
        psycopg2.extras.register_uuid()

        print(f"Connected to PostgreSQL database: {args.pg_dbname}")
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL: {e}", file=sys.stderr)
        return 1

    # Define table order based on dependencies
    table_order = [
        # Skip alembic_version as we already have a new migration history
        "tool_descriptions",
        "projects",
        "organization_secrets",
        "graph_runners",
        "data_sources",
        "components",
        "component_parameter_definitions",
        "comp_param_child_comps_relationships",
        "component_instances",
        "basic_parameters",
        "component_sub_inputs",
        "graph_runner_nodes",
        "graph_runner_edges",
        "project_env_binding",
        "api_keys",
        "ingestion_tasks",
    ]

    # Clear existing data if requested
    if args.clear:
        try:
            clear_tables(conn, table_order)
        except Exception as e:
            print(f"Error during table clearing: {e}", file=sys.stderr)
            conn.close()
            return 1

    # Temporarily disable foreign key constraints
    if args.disable_triggers:
        cursor = conn.cursor()
        cursor.execute("SET session_replication_role = 'replica';")
        print("Foreign key constraints temporarily disabled")

    # Get list of CSV files (excluding tables.csv)
    csv_files = [f for f in csv_dir.iterdir() if f.is_file() and f.suffix == ".csv" and f.name != "tables.csv"]
    csv_file_dict = {f.stem: f for f in csv_files}

    # Load each table in order
    total_tables = 0
    try:
        for table_name in table_order:
            if table_name in csv_file_dict:
                csv_file = csv_file_dict[table_name]
                try:
                    row_count = load_csv_to_table(conn, csv_file, table_name, args.disable_triggers)
                    print(f"Imported table '{table_name}' with {row_count} rows")
                    total_tables += 1
                except Exception as e:
                    print(f"Error importing table '{table_name}': {e}", file=sys.stderr)
                    if not args.disable_triggers:
                        print("Consider using --disable_triggers to ignore foreign key constraints")
                        raise
            else:
                print(f"Warning: No CSV file found for table '{table_name}'")
    except Exception:
        conn.rollback()
        print("Transaction rolled back due to error")
    else:
        conn.commit()
        print("All data imported and committed successfully")

    # Re-enable foreign key constraints
    if args.disable_triggers:
        cursor = conn.cursor()
        try:
            cursor.execute("SET session_replication_role = 'origin';")
            print("Foreign key constraints re-enabled")
        except psycopg2.Error:
            # If there was an error, we might need a fresh cursor
            conn.rollback()
            cursor = conn.cursor()
            cursor.execute("SET session_replication_role = 'origin';")
            print("Foreign key constraints re-enabled (after rollback)")

    conn.close()

    # Print summary
    print("\nImport Summary:")
    print(f"Total tables imported: {total_tables}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
