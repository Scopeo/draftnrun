"""Backup QA Projects to JSON

This script exports all projects from a specific organization to JSON files.

Usage:
    uv run python -m ada_backend.scripts.backup_qa_projects --organization-id <UUID> --output-dir <PATH>

Example:
    uv run python -m ada_backend.scripts.backup_qa_projects \\
        --organization-id 37b7d67f-8f29-4fce-8085-19dea582f605 \\
        --output-dir ./qa_backups
"""

import argparse
import json
from pathlib import Path
from uuid import UUID
from typing import List

from sqlalchemy.orm import Session

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ada_backend.database import models as db
from ada_backend.services.graph.load_copy_graph_service import load_copy_graph_service


def get_organization_projects(session: Session, organization_id: UUID) -> List[db.Project]:
    """Get all projects for an organization."""
    return session.query(db.Project).filter(db.Project.organization_id == organization_id).all()


def backup_organization_projects(organization_id: UUID, output_dir: Path, db_url: str) -> None:
    """Backup all projects from an organization to JSON files."""

    org_backup_dir = output_dir / str(organization_id)
    org_backup_dir.mkdir(parents=True, exist_ok=True)

    # Create database connection using provided URL
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        projects = get_organization_projects(session, organization_id)

        if not projects:
            print(f"❌ No projects found for organization {organization_id}")
            return

        print(f"📦 Found {len(projects)} projects to backup")

        metadata = {"organization_id": str(organization_id), "project_count": len(projects), "projects": []}

        for project in projects:
            print(f"  📝 Backing up project: {project.name} ({project.id})")

            # Get environment bindings via relationship
            env_bindings = project.envs

            project_metadata = {
                "id": str(project.id),
                "name": project.name,
                "type": project.type,
                "description": project.description,
                "created_at": str(project.created_at),
                "updated_at": str(project.updated_at),
                "environments": [],
            }

            for binding in env_bindings:
                try:
                    graph_data = load_copy_graph_service(
                        session=session, project_id_to_copy=project.id, graph_runner_id_to_copy=binding.graph_runner_id
                    )

                    env_data = {
                        "environment": binding.environment,
                        "graph_runner_id": str(binding.graph_runner_id),
                        "graph": {
                            "component_instances": [
                                {
                                    "id": str(ci.id),
                                    "name": ci.name,
                                    "is_start_node": ci.is_start_node,
                                    "component_id": str(ci.component_id),
                                    "tool_description": (
                                        ci.tool_description.model_dump(mode="json") if ci.tool_description else None
                                    ),
                                    "parameters": [
                                        {"name": p.name, "value": p.value, "order": p.order} for p in ci.parameters
                                    ],
                                    "integration": ci.integration.model_dump(mode="json") if ci.integration else None,
                                }
                                for ci in graph_data.component_instances
                            ],
                            "relationships": [
                                {
                                    "parent_component_instance_id": str(r.parent_component_instance_id),
                                    "child_component_instance_id": str(r.child_component_instance_id),
                                    "parameter_name": r.parameter_name,
                                    "order": r.order,
                                }
                                for r in graph_data.relationships
                            ],
                            "edges": [
                                {
                                    "id": str(e.id),
                                    "origin": str(e.origin),
                                    "destination": str(e.destination),
                                    "order": e.order,
                                }
                                for e in graph_data.edges
                            ],
                        },
                    }

                    project_metadata["environments"].append(env_data)

                except Exception as e:
                    print(f"    ⚠️  Warning: Could not backup graph for env {binding.environment}: {e}")

            project_file = org_backup_dir / f"{project.id}_graph.json"
            with open(project_file, "w") as f:
                json.dump(project_metadata, f, indent=2)

            metadata["projects"].append(
                {
                    "id": str(project.id),
                    "name": project.name,
                    "type": project.type,
                    "environment_count": len(project_metadata["environments"]),
                }
            )

        metadata_file = org_backup_dir / "metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"\n✅ Backup completed successfully!")
        print(f"📁 Backup location: {org_backup_dir.absolute()}")
        print(f"📊 Backed up {len(projects)} projects")

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Backup all projects from a specific organization to JSON files")
    parser.add_argument("--organization-id", type=str, required=True, help="UUID of the organization to backup")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory where JSON backups will be saved")
    parser.add_argument(
        "--db-url", type=str, required=True, help="Database connection URL (e.g., postgresql://user:pass@host:5432/db)"
    )

    args = parser.parse_args()

    try:
        org_id = UUID(args.organization_id)
    except ValueError:
        print(f"❌ Error: Invalid UUID format: {args.organization_id}")
        return 1

    output_directory = Path(args.output_dir)

    try:
        backup_organization_projects(org_id, output_directory, args.db_url)
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
