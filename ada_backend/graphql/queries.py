from datetime import datetime
from uuid import UUID

import strawberry
from strawberry.types import Info

from ada_backend.graphql.types.project_types import ProjectType, GraphRunnerEnvType
from ada_backend.services.project_service import get_project_service, get_projects_by_organization


# TODO: Put query resolvers in separate files
@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello from GraphQL (Query placeholder)"

    @strawberry.field
    def project(self, info: Info, id: UUID) -> ProjectType:
        project = get_project_service(session=info.context.db, project_id=id)
        return ProjectType(
            id=project.project_id,
            name=project.project_name,
            description=project.description,
            companion_image_url=project.companion_image_url,
            organization_id=project.organization_id,
            created_at=datetime.fromisoformat(project.created_at),
            updated_at=datetime.fromisoformat(project.updated_at),
            graph_runners=[
                GraphRunnerEnvType(
                    id=gr.graph_runner_id,
                    env=gr.env,
                )
                for gr in project.graph_runners
            ],
        )

    @strawberry.field
    def projects_by_organization(self, info: Info, org_id: UUID) -> list[ProjectType]:
        projects = get_projects_by_organization(session=info.context.db, organization_id=org_id)
        return [
            ProjectType(
                id=project.project_id,
                name=project.project_name,
                description=project.description,
                companion_image_url=project.companion_image_url,
                organization_id=project.organization_id,
                created_at=datetime.fromisoformat(project.created_at),
                updated_at=datetime.fromisoformat(project.updated_at),
            )
            for project in projects
        ]
