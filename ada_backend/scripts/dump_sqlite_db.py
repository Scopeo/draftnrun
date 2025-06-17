#!/usr/bin/env python3
import argparse
import csv
import sqlite3
import sys
from pathlib import Path


def dump_table_to_csv(conn, table_name, output_dir):
    cursor = conn.cursor()

    # Get all rows
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    # Get column names
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]

    # Write to CSV
    csv_path = output_dir / f"{table_name}.csv"
    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(columns)
        writer.writerows(rows)

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Dump SQLite database to CSV files")
    parser.add_argument("--db_path", type=str, required=True, help="Path to SQLite database file")
    parser.add_argument("--output_dir", type=str, required=True, help="Directory to store CSV files")

    args = parser.parse_args()

    db_path = Path(args.db_path)
    output_dir = Path(args.output_dir)

    # Check if database file exists
    if not db_path.exists():
        print(f"Error: Database file '{db_path}' not found.", file=sys.stderr)
        return 1

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Connect to SQLite database
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        return 1

    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    # Filter out SQLite system tables
    tables = [table for table in tables if not table.startswith("sqlite_")]

    # Write table list to CSV
    tables_csv_path = output_dir / "tables.csv"
    with open(tables_csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["table_name"])
        writer.writerows([[table] for table in tables])

    # Dump each table to CSV
    table_stats = []
    for table in tables:
        try:
            row_count = dump_table_to_csv(conn, table, output_dir)
            table_stats.append((table, row_count))
            print(f"Exported table '{table}' with {row_count} rows")
        except Exception as e:
            print(f"Error exporting table '{table}': {e}", file=sys.stderr)

    conn.close()

    # Print summary
    print("\nExport Summary:")
    print(f"Total tables: {len(tables)}")
    print(f"CSV files written to: {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
