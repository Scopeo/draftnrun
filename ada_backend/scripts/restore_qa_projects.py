"""Restore QA Projects from JSON Backup

This script imports projects from JSON backup files created by backup_qa_projects.py.

Usage:
    uv run python -m ada_backend.scripts.restore_qa_projects --backup-dir <PATH> --db-url <URL>

Example:
    uv run python -m ada_backend.scripts.restore_qa_projects \\
        --backup-dir ./qa_backups/18012b84-b605-4669-95bf-55aa16c5513c \\
        --db-url postgresql://user:pass@host:5432/ada_backend
"""

import argparse
import json
from pathlib import Path
from uuid import UUID, uuid4
from typing import Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ada_backend.database import models as db
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema, ComponentRelationshipSchema
from ada_backend.schemas.pipeline.graph_schema import EdgeSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateSchema


def create_project_from_backup(session: Session, project_data: Dict[str, Any], organization_id: UUID) -> UUID:
    """Create a new project from backup data."""

    # Create the project
    project = db.Project(
        id=uuid4(),
        name=project_data["name"],
        type=project_data["type"],
        description=project_data.get("description"),
        organization_id=organization_id,
        created_at=project_data.get("created_at"),
        updated_at=project_data.get("updated_at"),
    )

    session.add(project)
    session.flush()  # Get the project ID

    print(f"  ✅ Created project: {project.name} ({project.id})")
    return project.id


def create_graph_from_backup(session: Session, project_id: UUID, env_data: Dict[str, Any]) -> UUID:
    """Create a graph runner from backup environment data."""

        # Create graph runner
        # For draft environments, tag_version must be None to allow modifications
        tag_version = None if env_data["environment"] == "draft" else "restored"
        graph_runner = db.GraphRunner(
            id=uuid4(),
            tag_version=tag_version,
            created_at=env_data.get("created_at"),
            updated_at=env_data.get("updated_at"),
        )

    session.add(graph_runner)
    session.flush()

    # Create environment binding
    env_binding = db.ProjectEnvironmentBinding(
        project_id=project_id, graph_runner_id=graph_runner.id, environment=env_data["environment"]
    )

    session.add(env_binding)
    session.flush()

    print(f"    ✅ Created graph runner for env {env_data['environment']} ({graph_runner.id})")
    return graph_runner.id


def restore_organization_projects(backup_dir: Path, db_url: str, organization_id: UUID) -> None:
    """Restore all projects from backup directory to database."""

    if not backup_dir.exists():
        print(f"❌ Error: Backup directory does not exist: {backup_dir}")
        return

    # Create database connection
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        # Read metadata
        metadata_file = backup_dir / "metadata.json"
        if not metadata_file.exists():
            print(f"❌ Error: Metadata file not found: {metadata_file}")
            return

        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        print(f"📦 Found {metadata['project_count']} projects to restore")

        # Process each project file
        for project_info in metadata["projects"]:
            project_id = project_info["id"]
            project_file = backup_dir / f"{project_id}_graph.json"

            if not project_file.exists():
                print(f"⚠️  Warning: Project file not found: {project_file}")
                continue

            print(f"📝 Restoring project: {project_info['name']} ({project_id})")

            with open(project_file, "r") as f:
                project_data = json.load(f)

            # Create the project
            new_project_id = create_project_from_backup(session, project_data, organization_id)

            # Create graph runners for each environment
            for env_data in project_data.get("environments", []):
                try:
                    graph_runner_id = create_graph_from_backup(session, new_project_id, env_data)

                    # Deploy the graph using the existing service
                    graph_data = env_data["graph"]

                    # Convert backup data to schemas
                    component_instances = [
                        ComponentInstanceSchema(
                            id=uuid4(),
                            name=ci["name"],
                            is_start_node=ci["is_start_node"],
                            component_id=UUID(ci["component_id"]),
                            tool_description=ci.get("tool_description"),
                            integration=ci.get("integration"),
                            parameters=[
                                PipelineParameterSchema(name=p["name"], value=p["value"], order=p["order"])
                                for p in ci.get("parameters", [])
                            ],
                        )
                        for ci in graph_data["component_instances"]
                    ]

                    relationships = [
                        ComponentRelationshipSchema(
                            parent_component_instance_id=UUID(rel["parent_component_instance_id"]),
                            child_component_instance_id=UUID(rel["child_component_instance_id"]),
                            parameter_name=rel["parameter_name"],
                            order=rel.get("order"),
                        )
                        for rel in graph_data["relationships"]
                    ]

                    edges = [
                        EdgeSchema(
                            id=uuid4(),
                            origin=UUID(edge["origin"]),
                            destination=UUID(edge["destination"]),
                            order=edge.get("order"),
                        )
                        for edge in graph_data["edges"]
                    ]

                    # Update the graph with the backup data
                    graph_update = GraphUpdateSchema(
                        component_instances=component_instances, relationships=relationships, edges=edges
                    )

                    # Use asyncio to run the async function
                    import asyncio

                    asyncio.run(
                        update_graph_service(
                            session=session,
                            graph_runner_id=graph_runner_id,
                            project_id=new_project_id,
                            graph_project=graph_update,
                        )
                    )

                    print(f"    ✅ Deployed graph for env {env_data['environment']}")

                except Exception as e:
                    print(f"    ⚠️  Warning: Could not restore graph for env {env_data['environment']}: {e}")

        session.commit()
        print(f"\n✅ Restore completed successfully!")
        print(f"📊 Restored {metadata['project_count']} projects")

    except Exception as e:
        session.rollback()
        print(f"❌ Error during restore: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Restore projects from JSON backup files")
    parser.add_argument("--backup-dir", type=str, required=True, help="Directory containing JSON backup files")
    parser.add_argument("--db-url", type=str, required=True, help="Database connection URL")
    parser.add_argument("--organization-id", type=str, required=True, help="UUID of the organization to restore to")

    args = parser.parse_args()

    try:
        org_id = UUID(args.organization_id)
    except ValueError:
        print(f"❌ Error: Invalid UUID format: {args.organization_id}")
        return 1

    backup_directory = Path(args.backup_dir)

    try:
        restore_organization_projects(backup_directory, args.db_url, org_id)
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
