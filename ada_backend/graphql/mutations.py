from typing import Optional
from uuid import UUID

import strawberry
from strawberry.types import Info

from ada_backend.graphql.types.graph_types import (
    AddEdgePayload,
    DeleteComponentInstancePayload,
    DeleteEdgePayload,
    UpdateComponentInstancePayload,
)
from ada_backend.graphql.types.project_types import GraphRunnerEnvType, ProjectType
from ada_backend.repositories.edge_repository import delete_edge
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.project_schema import ProjectSchema
from ada_backend.services.graph.update_graph_service import (
    add_edge_service,
    delete_component_instance_service,
    save_component_instance_service,
)
from ada_backend.services.project_service import create_workflow


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

    @strawberry.mutation
    async def update_component_instance(
        self,
        info: Info,
        project_id: UUID,
        graph_runner_id: UUID,
        instance: str,
    ) -> UpdateComponentInstancePayload:
        """Update a single component instance and its field expressions / input ports.

        ``instance`` is a JSON string matching ComponentInstanceSchema.
        Edges are never touched by this mutation — use addEdge / deleteEdge for that.
        """
        user_id = await info.context.get_user_id()
        instance_schema = ComponentInstanceSchema.model_validate_json(instance)
        result = await save_component_instance_service(
            session=info.context.db,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
            instance=instance_schema,
            user_id=user_id,
        )
        return UpdateComponentInstancePayload(
            component_instance_id=result.component_instance_id,
            component_instance=result.component_instance.model_dump(mode="json"),
        )

    @strawberry.mutation
    async def delete_component_instance(
        self,
        info: Info,
        graph_runner_id: UUID,
        instance_id: UUID,
    ) -> DeleteComponentInstancePayload:
        """Remove a component instance from the graph.

        All edges connected to the instance are deleted first.
        Returns the deleted instance ID and the list of deleted edge IDs so the
        frontend can update the canvas without a full graph refetch.
        """
        user_id = await info.context.get_user_id()
        result = delete_component_instance_service(
            session=info.context.db,
            graph_runner_id=graph_runner_id,
            instance_id=instance_id,
            user_id=user_id,
        )
        return DeleteComponentInstancePayload(
            deleted_instance_id=result["instance_id"],
            deleted_edge_ids=result["deleted_edge_ids"],
        )

    @strawberry.mutation
    def add_edge(
        self,
        info: Info,
        graph_runner_id: UUID,
        edge_id: UUID,
        source_node_id: UUID,
        target_node_id: UUID,
        order: Optional[int] = None,
    ) -> AddEdgePayload:
        """Create or update an edge between two component instance nodes."""
        add_edge_service(
            session=info.context.db,
            graph_runner_id=graph_runner_id,
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            order=order,
        )
        return AddEdgePayload(edge_id=edge_id)

    @strawberry.mutation
    def delete_edge(
        self,
        info: Info,
        edge_id: UUID,
    ) -> DeleteEdgePayload:
        """Delete an existing edge by its ID."""
        delete_edge(info.context.db, edge_id)
        return DeleteEdgePayload(deleted_edge_id=edge_id)
