import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import UserRights, user_has_access_to_project_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.pipeline.graph_schema import (
    ComponentCreateV2Schema,
    ComponentGetV2Response,
    ComponentUpdateV2Schema,
    ComponentV2Response,
    GraphGetV2Response,
    GraphTopologySaveV2Schema,
    GraphUpdateResponse,
)
from ada_backend.services.graph import graph_mutation_helpers
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.graph_v2_mapper_service import graph_get_to_graph_v2_response

router = APIRouter(prefix="/v2/projects/{project_id}/graph", tags=["Graph"])
LOGGER = logging.getLogger(__name__)


@router.get("/{graph_runner_id}", summary="Get Project Graph V2", response_model=GraphGetV2Response)
def get_project_graph_v2(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphGetV2Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        # TODO: replace get_graph_service (deprecated) with its successor
        graph = get_graph_service(session, project_id, graph_runner_id)
        return graph_get_to_graph_v2_response(graph)
    except ValueError as e:
        LOGGER.warning("Invalid v2 graph payload for runner %s: %s", graph_runner_id, e)
        raise HTTPException(status_code=400, detail="Invalid v2 graph payload")


@router.get(
    "/{graph_runner_id}/components/{instance_id}",
    summary="Get Component Instance V2",
    response_model=ComponentGetV2Response,
)
def get_component_v2(
    project_id: UUID,
    graph_runner_id: UUID,
    instance_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> ComponentGetV2Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    return graph_mutation_helpers.get_component_v2(session, graph_runner_id, project_id, instance_id)


@router.post(
    "/{graph_runner_id}/components",
    summary="Create Component Instance V2",
    response_model=ComponentV2Response,
    status_code=201,
)
def create_component_v2(
    project_id: UUID,
    graph_runner_id: UUID,
    payload: ComponentCreateV2Schema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> ComponentV2Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return graph_mutation_helpers.create_component_v2(session, graph_runner_id, project_id, user.id, payload)
    except ValueError as e:
        LOGGER.warning("Invalid component payload for runner %s: %s", graph_runner_id, e)
        raise HTTPException(status_code=400, detail="Invalid component payload")


@router.put(
    "/{graph_runner_id}/components/{instance_id}",
    summary="Update Component Instance V2",
    response_model=ComponentV2Response,
)
def update_component_v2(
    project_id: UUID,
    graph_runner_id: UUID,
    instance_id: UUID,
    payload: ComponentUpdateV2Schema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> ComponentV2Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return graph_mutation_helpers.update_component_v2(
            session, graph_runner_id, project_id, instance_id, user.id, payload
        )
    except ValueError as e:
        LOGGER.warning("Invalid component update payload for instance %s: %s", instance_id, e)
        raise HTTPException(status_code=400, detail="Invalid component update payload")


@router.delete(
    "/{graph_runner_id}/components/{instance_id}",
    summary="Delete Component Instance V2",
    status_code=204,
)
def delete_component_v2(
    project_id: UUID,
    graph_runner_id: UUID,
    instance_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        graph_mutation_helpers.delete_component_v2(session, graph_runner_id, project_id, instance_id, user.id)
    except ValueError as e:
        LOGGER.warning("Invalid component deletion request for instance %s: %s", instance_id, e)
        raise HTTPException(status_code=400, detail="Invalid component deletion request")


@router.put(
    "/{graph_runner_id}/map",
    summary="Update Graph Topology V2",
    response_model=GraphUpdateResponse,
)
def update_graph_topology_v2(
    project_id: UUID,
    graph_runner_id: UUID,
    payload: GraphTopologySaveV2Schema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphUpdateResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return graph_mutation_helpers.save_graph_topology_v2(session, graph_runner_id, project_id, user.id, payload)
    except ValueError as e:
        LOGGER.warning("Invalid graph topology payload for runner %s: %s", graph_runner_id, e)
        raise HTTPException(status_code=400, detail="Invalid graph topology payload")
