from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.repositories.project_repository import get_project
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.pipeline.graph_schema import (
    GraphDeployResponse,
    GraphGetResponse,
    GraphUpdateResponse,
    GraphUpdateSchema,
)
from ada_backend.database.setup_db import get_db

from ada_backend.services.graph.deploy_graph_service import deploy_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.services.graph.get_graph_service import get_graph_service

router = APIRouter(
    prefix="/projects/{project_id}/graph",
)


@router.get("/{graph_runner_id}", summary="Get Project Graph", response_model=GraphGetResponse, tags=["Graph"])
def get_project_graph(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value))
    ],
    sqlaclhemy_db_session: Session = Depends(get_db),
) -> GraphGetResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_graph_service(sqlaclhemy_db_session, project_id, graph_runner_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.put(
    "/{graph_runner_id}", summary="Update Project Graph Runner", response_model=GraphUpdateResponse, tags=["Graph"]
)
async def update_project_pipeline(
    project_id: UUID,
    graph_runner_id: UUID,
    project_graph: GraphUpdateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphUpdateResponse:
    """
    Replace an entire pipeline for a project.
    Creates or updates all component instances, their parameters, and relationships.
    Follows PUT semantics - completely replaces existing pipeline state.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    project = get_project(session, project_id=project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return await update_graph_service(
            session=session,
            graph_project=project_graph,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{graph_runner_id}/deploy", summary="Deploy Graph Runner", response_model=GraphDeployResponse, tags=["Graph"]
)
def deploy_graph(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> GraphDeployResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    project = get_project(session, project_id=project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return deploy_graph_service(
            session=session,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
