"""Clone QA Projects from Staging to Preprod

This script clones all projects from a specific organization from staging to preprod
using the clone service, which automatically handles ID generation and dependencies.

Usage:
    uv run python -m ada_backend.scripts.clone_qa_projects --organization-id <UUID> --staging-db-url <URL> --preprod-db-url <URL>

Example:
    uv run python -m ada_backend.scripts.clone_qa_projects \\
        --organization-id <ORG_UUID> \\
        --staging-db-url "postgresql://user:pass@staging-host:5432/db" \\
        --preprod-db-url "postgresql://user:pass@preprod-host:5432/db"
"""

import argparse
from pathlib import Path
from uuid import UUID
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ada_backend.database import models as db
from ada_backend.services.graph.deploy_graph_service import clone_graph_runner
from ada_backend.repositories.env_repository import bind_graph_runner_to_project
from ada_backend.database.models import EnvType


def get_organization_projects(session: Session, organization_id: UUID) -> List[db.Project]:
    """Get all projects for an organization."""
    return session.query(db.Project).filter(db.Project.organization_id == organization_id).all()


def clone_organization_projects(organization_id: UUID, staging_db_url: str, preprod_db_url: str) -> None:
    """Clone all projects from an organization from staging to preprod."""

    # Create staging database connection
    staging_engine = create_engine(staging_db_url)
    StagingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=staging_engine)
    staging_session = StagingSessionLocal()

    # Create preprod database connection
    preprod_engine = create_engine(preprod_db_url)
    PreprodSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=preprod_engine)
    preprod_session = PreprodSessionLocal()

    try:
        # Get projects from staging
        staging_projects = get_organization_projects(staging_session, organization_id)

        if not staging_projects:
            print(f"❌ No projects found for organization {organization_id} in staging")
            return

        print(f"📦 Found {len(staging_projects)} projects to clone from staging")

        cloned_count = 0

        for project in staging_projects:
            print(f"  📝 Cloning project: {project.name} ({project.id})")

            try:
                # Create the project in preprod using the correct polymorphic approach
                if project.type.value == "workflow":
                    new_project = db.WorkflowProject(
                        id=project.id,  # Keep the same ID for consistency
                        name=project.name,
                        type=project.type,
                        description=project.description,
                        organization_id=project.organization_id,
                    )
                elif project.type.value == "agent":
                    new_project = db.AgentProject(
                        id=project.id,  # Keep the same ID for consistency
                        name=project.name,
                        type=project.type,
                        description=project.description,
                        organization_id=project.organization_id,
                    )
                else:
                    new_project = db.Project(
                        id=project.id,  # Keep the same ID for consistency
                        name=project.name,
                        type=project.type,
                        description=project.description,
                        organization_id=project.organization_id,
                    )

                preprod_session.add(new_project)
                preprod_session.commit()

                # Clone each environment's graph runner
                for binding in project.envs:
                    if binding.graph_runner_id:
                        print(f"    🔄 Cloning graph runner {binding.graph_runner_id} for env {binding.environment}")

                        # Clone the graph runner
                        new_graph_runner_id = clone_graph_runner(
                            session=preprod_session,
                            graph_runner_id_to_copy=binding.graph_runner_id,
                            project_id=project.id,
                        )

                        # Bind the new graph runner to the project
                        bind_graph_runner_to_project(
                            session=preprod_session,
                            graph_runner_id=new_graph_runner_id,
                            project_id=project.id,
                            env=binding.environment,
                        )

                        print(f"    ✅ Cloned graph runner {new_graph_runner_id} for env {binding.environment}")

                cloned_count += 1
                print(f"  ✅ Successfully cloned project: {project.name}")

            except Exception as e:
                print(f"    ❌ Error cloning project {project.name}: {e}")
                preprod_session.rollback()
                continue

        print(f"\n✅ Clone completed successfully!")
        print(f"📊 Cloned {cloned_count} out of {len(staging_projects)} projects")

    finally:
        staging_session.close()
        preprod_session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Clone all projects from a specific organization from staging to preprod"
    )
    parser.add_argument("--organization-id", type=str, required=True, help="UUID of the organization to clone")
    parser.add_argument("--staging-db-url", type=str, required=True, help="Staging database connection URL")
    parser.add_argument("--preprod-db-url", type=str, required=True, help="Preprod database connection URL")

    args = parser.parse_args()

    try:
        org_id = UUID(args.organization_id)
    except ValueError:
        print(f"❌ Error: Invalid UUID format: {args.organization_id}")
        return 1

    try:
        clone_organization_projects(org_id, args.staging_db_url, args.preprod_db_url)
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
