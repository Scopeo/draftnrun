#!/usr/bin/env python3
import csv
import sys
from pathlib import Path


def fix_tool_descriptions_csv(input_file, output_file):
    """Fix empty descriptions in tool_descriptions.csv by adding default values"""

    with open(input_file, "r") as infile:
        reader = csv.reader(infile)
        headers = next(reader)
        rows = list(reader)

    # Find index of description column
    desc_idx = headers.index("description") if "description" in headers else -1
    name_idx = headers.index("name") if "name" in headers else -1

    if desc_idx == -1:
        print("Warning: No description column found in tool_descriptions.csv")
        return

    # Fix empty descriptions
    fixed_rows = []
    fixed_count = 0

    for row in rows:
        if desc_idx >= len(row) or not row[desc_idx]:
            # Create a copy of the row
            fixed_row = list(row)

            # Ensure the row is long enough
            while len(fixed_row) <= desc_idx:
                fixed_row.append("")

            # Set a default description based on the name or a generic one
            if name_idx != -1 and name_idx < len(fixed_row) and fixed_row[name_idx]:
                fixed_row[desc_idx] = f"Default description for {fixed_row[name_idx]}"
            else:
                fixed_row[desc_idx] = "Default description"

            fixed_rows.append(fixed_row)
            fixed_count += 1
        else:
            fixed_rows.append(row)

    # Write the fixed CSV
    with open(output_file, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(headers)
        writer.writerows(fixed_rows)

    return fixed_count


def fix_graph_runner_nodes_csv(input_file, output_file):
    """Fix node_type enum values in graph_runner_nodes.csv"""

    with open(input_file, "r") as infile:
        reader = csv.reader(infile)
        headers = next(reader)
        rows = list(reader)

    # Find index of node_type column
    node_type_idx = headers.index("node_type") if "node_type" in headers else -1

    if node_type_idx == -1:
        print("Warning: No node_type column found in graph_runner_nodes.csv")
        return

    # Fix node_type values
    fixed_rows = []
    fixed_count = 0

    for row in rows:
        if node_type_idx < len(row):
            # Create a copy of the row
            fixed_row = list(row)

            # Fix node_type values
            if fixed_row[node_type_idx] == "component":
                fixed_row[node_type_idx] = "component_instance"
                fixed_count += 1
            elif fixed_row[node_type_idx] == "graph":
                fixed_row[node_type_idx] = "graph_runner"
                fixed_count += 1

            fixed_rows.append(fixed_row)
        else:
            fixed_rows.append(row)

    # Write the fixed CSV
    with open(output_file, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(headers)
        writer.writerows(fixed_rows)

    return fixed_count


def fix_project_env_binding_csv(input_file, output_file):
    """Fix environment enum values in project_env_binding.csv (PRODUCTION → production)"""

    with open(input_file, "r") as infile:
        reader = csv.reader(infile)
        headers = next(reader)
        rows = list(reader)

    # Find index of environment column
    env_idx = headers.index("environment") if "environment" in headers else -1

    if env_idx == -1:
        print("Warning: No environment column found in project_env_binding.csv")
        return

    # Fix environment values
    fixed_rows = []
    fixed_count = 0

    for row in rows:
        if env_idx < len(row):
            # Create a copy of the row
            fixed_row = list(row)

            # Fix environment values (case-sensitive issue)
            if fixed_row[env_idx] == "PRODUCTION":
                fixed_row[env_idx] = "production"
                fixed_count += 1
            elif fixed_row[env_idx] == "DRAFT":
                fixed_row[env_idx] = "draft"
                fixed_count += 1

            fixed_rows.append(fixed_row)
        else:
            fixed_rows.append(row)

    # Write the fixed CSV
    with open(output_file, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(headers)
        writer.writerows(fixed_rows)

    return fixed_count


def fix_ingestion_tasks_csv(input_file, output_file):
    """Fix source_type and status enum values in ingestion_tasks.csv"""

    with open(input_file, "r") as infile:
        reader = csv.reader(infile)
        headers = next(reader)
        rows = list(reader)

    # Find indices of source_type and status columns
    source_type_idx = headers.index("source_type") if "source_type" in headers else -1
    status_idx = headers.index("status") if "status" in headers else -1

    if source_type_idx == -1 and status_idx == -1:
        print("Warning: Neither source_type nor status column found in ingestion_tasks.csv")
        return

    # Fix source_type and status values
    fixed_rows = []
    fixed_count = 0

    for row in rows:
        # Create a copy of the row
        fixed_row = list(row)

        # Fix source_type values (uppercase to lowercase)
        if source_type_idx != -1 and source_type_idx < len(fixed_row) and fixed_row[source_type_idx]:
            if (
                fixed_row[source_type_idx].isupper()
                and fixed_row[source_type_idx].lower() != fixed_row[source_type_idx]
            ):
                fixed_row[source_type_idx] = fixed_row[source_type_idx].lower()
                fixed_count += 1

        # Fix status values (uppercase to lowercase)
        if status_idx != -1 and status_idx < len(fixed_row) and fixed_row[status_idx]:
            if fixed_row[status_idx].isupper() and fixed_row[status_idx].lower() != fixed_row[status_idx]:
                fixed_row[status_idx] = fixed_row[status_idx].lower()
                fixed_count += 1

        fixed_rows.append(fixed_row)

    # Write the fixed CSV
    with open(output_file, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(headers)
        writer.writerows(fixed_rows)

    return fixed_count


def copy_csv_file(input_file, output_file):
    """Copy CSV file without modifications"""
    with open(input_file, "r") as infile, open(output_file, "w", newline="") as outfile:
        outfile.write(infile.read())
    return 0


def process_all_csvs(input_dir, output_dir):
    """Process all CSV files in the input directory and save to output directory"""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    # Create output directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process each CSV file
    csv_files = [f for f in input_dir.iterdir() if f.is_file() and f.suffix == ".csv"]

    total_fixed = 0
    for csv_file in csv_files:
        output_file = output_dir / csv_file.name

        # Special handling for specific files
        if csv_file.name == "tool_descriptions.csv":
            fixed_count = fix_tool_descriptions_csv(csv_file, output_file)
            if fixed_count:
                total_fixed += fixed_count
                print(f"Fixed {fixed_count} rows in {csv_file.name}")
            else:
                print(f"Processed {csv_file.name} (no fixes needed)")
        elif csv_file.name == "graph_runner_nodes.csv":
            fixed_count = fix_graph_runner_nodes_csv(csv_file, output_file)
            if fixed_count:
                total_fixed += fixed_count
                print(f"Fixed {fixed_count} rows in {csv_file.name}")
            else:
                print(f"Processed {csv_file.name} (no fixes needed)")
        elif csv_file.name == "project_env_binding.csv":
            fixed_count = fix_project_env_binding_csv(csv_file, output_file)
            if fixed_count:
                total_fixed += fixed_count
                print(f"Fixed {fixed_count} rows in {csv_file.name}")
            else:
                print(f"Processed {csv_file.name} (no fixes needed)")
        elif csv_file.name == "ingestion_tasks.csv":
            fixed_count = fix_ingestion_tasks_csv(csv_file, output_file)
            if fixed_count:
                total_fixed += fixed_count
                print(f"Fixed {fixed_count} rows in {csv_file.name}")
            else:
                print(f"Processed {csv_file.name} (no fixes needed)")
        else:
            # Just copy other files
            copy_csv_file(csv_file, output_file)
            print(f"Copied {csv_file.name}")

    return total_fixed


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input_dir> <output_dir>")
        return 1

    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Error: Input directory '{input_dir}' not found or is not a directory")
        return 1

    total_fixed = process_all_csvs(input_dir, output_dir)
    print(f"\nProcessing complete. Fixed {total_fixed} total rows.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
