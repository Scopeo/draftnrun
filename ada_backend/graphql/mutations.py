from typing import Optional
from uuid import UUID

import strawberry
from strawberry.types import Info

from ada_backend.graphql.types.project_types import GraphRunnerEnvType, ProjectType
from ada_backend.services.project_service import create_workflow
from ada_backend.schemas.project_schema import ProjectSchema


# TODO: Put mutation resolvers in separate files
@strawberry.type
class Mutation:
    @strawberry.mutation
    def placeholder(self) -> str:
        return "Hello from GraphQL (Mutation placeholder)"

    @strawberry.mutation
    def create_project(
        self,
        info: Info,
        id: UUID,
        name: str,
        org_id: UUID,
        description: Optional[str] = None,
    ) -> ProjectType:
        project_w_gr_schema = create_workflow(
            session=info.context.db,
            organization_id=org_id,
            project_schema=ProjectSchema(
                project_id=id,
                project_name=name,
                description=description,
            ),
        )
        return ProjectType(
            **project_w_gr_schema.model_dump(exclude={"project_id", "project_name", "graph_runners"}),
            id=project_w_gr_schema.project_id,
            name=project_w_gr_schema.project_name,
            graph_runners=[
                GraphRunnerEnvType(
                    id=gr.graph_runner_id,
                    env=gr.env,
                )
                for gr in project_w_gr_schema.graph_runners
            ],
        )
