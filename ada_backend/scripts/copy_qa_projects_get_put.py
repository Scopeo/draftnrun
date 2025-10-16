"""Copy QA Projects from Staging to Preprod using GET → PUT approach

This script copies all projects from a specific organization from staging to preprod
using the get_graph_service and update_graph_service, which automatically handles
ID generation and dependencies.

FIXED: Now uses insert_project() to properly create polymorphic inheritance records
(WorkflowProject/AgentProject) instead of just base Project records.

Usage:
    uv run python -m ada_backend.scripts.copy_qa_projects_get_put --organization-id <UUID> --staging-db-url <URL> --preprod-db-url <URL>

Example:
    uv run python -m ada_backend.scripts.copy_qa_projects_get_put \\
        --organization-id <ORG_UUID> \\
        --staging-db-url "postgresql://user:pass@staging-host:5432/db" \\
        --preprod-db-url "postgresql://user:pass@preprod-host:5432/db"
"""

import argparse
from uuid import UUID, uuid4
from typing import List
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ada_backend.database.models import Project, ProjectEnvironmentBinding
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateSchema
from ada_backend.database.models import EnvType
from ada_backend.repositories.project_repository import insert_project

LOGGER = logging.getLogger(__name__)


def clear_ids_for_new_creation(graph_data):
    """Clear IDs from graph data so new ones can be generated"""
    # Clear component instance IDs
    for instance in graph_data.component_instances:
        instance.id = None

    # Clear relationship IDs and instance references
    for relationship in graph_data.relationships:
        relationship.parent_component_instance_id = None
        relationship.child_component_instance_id = None

    # Clear edge IDs and node references
    for edge in graph_data.edges:
        edge.id = None
        edge.origin = None  # Will be set by the service
        edge.destination = None

    # Clear port mapping instance references
    for port_mapping in graph_data.port_mappings:
        port_mapping.source_instance_id = None
        port_mapping.target_instance_id = None

    return graph_data


def copy_qa_projects_get_put(organization_id: UUID, staging_db_url: str, preprod_db_url: str) -> None:
    """Copy QA projects from staging to preprod using GET → PUT approach"""

    # Create database connections
    staging_engine = create_engine(staging_db_url)
    preprod_engine = create_engine(preprod_db_url)

    StagingSession = sessionmaker(bind=staging_engine)
    PreprodSession = sessionmaker(bind=preprod_engine)

    staging_session = StagingSession()
    preprod_session = PreprodSession()

    try:
        # Get all projects for the organization from staging
        staging_projects = staging_session.query(Project).filter(Project.organization_id == organization_id).all()

        print(f"📦 Found {len(staging_projects)} projects to copy from staging")

        copied_count = 0

        for project in staging_projects:
            print(f"  📝 Copying project: {project.name} ({project.id})")

            try:
                # Create the project in preprod using proper polymorphic inheritance
                # This ensures records are created in both projects table AND polymorphic tables
                new_project = insert_project(
                    session=preprod_session,
                    project_id=uuid4(),  # Generate new UUID
                    project_name=project.name,
                    organization_id=organization_id,
                    description=project.description,
                    project_type=project.type,  # This will create WorkflowProject or AgentProject
                )

                # Get environment bindings for this project
                env_bindings = (
                    staging_session.query(ProjectEnvironmentBinding)
                    .filter(ProjectEnvironmentBinding.project_id == project.id)
                    .all()
                )

                for binding in env_bindings:
                    try:
                        print(f"    🔄 Copying graph runner {binding.graph_runner_id} for env {binding.environment}")

                        # Get the complete graph data from staging
                        graph_data = get_graph_service(
                            session=staging_session, project_id=project.id, graph_runner_id=binding.graph_runner_id
                        )

                        # Clear IDs so new ones can be generated
                        graph_data = clear_ids_for_new_creation(graph_data)

                        # Create new graph runner in preprod
                        new_graph_runner_id = uuid4()

                        # Use update_graph_service to create the complete graph
                        update_graph_service(
                            session=preprod_session,
                            graph_runner_id=new_graph_runner_id,
                            project_id=new_project.id,
                            graph_project=GraphUpdateSchema(
                                component_instances=graph_data.component_instances,
                                relationships=graph_data.relationships,
                                edges=graph_data.edges,
                                port_mappings=graph_data.port_mappings,
                            ),
                            env=binding.environment,
                            bypass_validation=True,  # Skip draft validation for migration
                        )

                        print(
                            f"    ✅ Successfully copied graph runner {new_graph_runner_id} for env {binding.environment}"
                        )

                    except Exception as e:
                        print(f"    ❌ Error copying graph runner {binding.graph_runner_id}: {e}")
                        continue

                # Note: insert_project already commits, so we don't need to commit here
                print(f"  ✅ Successfully copied project: {project.name}")
                copied_count += 1

            except Exception as e:
                print(f"  ❌ Error copying project {project.name}: {e}")
                preprod_session.rollback()
                continue

        print(f"\n✅ Copy completed successfully!")
        print(f"📊 Copied {copied_count} out of {len(staging_projects)} projects")

    except Exception as e:
        print(f"❌ Error during copy process: {e}")
        preprod_session.rollback()
        raise
    finally:
        staging_session.close()
        preprod_session.close()


def main():
    parser = argparse.ArgumentParser(description="Copy QA projects from staging to preprod using GET → PUT approach")
    parser.add_argument("--organization-id", type=str, required=True, help="Organization UUID")
    parser.add_argument("--staging-db-url", type=str, required=True, help="Staging database URL")
    parser.add_argument("--preprod-db-url", type=str, required=True, help="Preprod database URL")

    args = parser.parse_args()

    try:
        organization_id = UUID(args.organization_id)
    except ValueError:
        print("❌ Invalid organization ID format. Must be a valid UUID.")
        return

    copy_qa_projects_get_put(
        organization_id=organization_id, staging_db_url=args.staging_db_url, preprod_db_url=args.preprod_db_url
    )


if __name__ == "__main__":
    main()
