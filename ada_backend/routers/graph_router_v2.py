import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.repositories.graph_runner_repository import get_component_nodes
from ada_backend.routers.auth_router import UserRights, user_has_access_to_project_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.pipeline.graph_schema import (
    ApiCallOutputPortTestRequest,
    ApiCallOutputPortTestResponse,
    ComponentCreateV2Schema,
    ComponentUpdateV2Schema,
    ComponentV2Response,
    GraphGetV2Response,
    GraphTopologySaveV2Schema,
    GraphUpdateResponse,
)
from ada_backend.services.graph import graph_mutation_helpers
from ada_backend.services.graph.api_call_auto_output_ports_service import (
    test_and_persist_api_call_get_auto_output_ports,
)
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.graph_v2_mapper_service import graph_get_to_graph_v2_response
from ada_backend.services.graph.graph_validation_utils import validate_graph_runner_belongs_to_project
from ada_backend.services.graph.update_graph_service import validate_graph_is_draft
from ada_backend.utils.redis_client import notify_graph_changed

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


@router.post(
    "/{graph_runner_id}/components/{instance_id}/api-call/test-output-ports",
    summary="Test API Call GET Response Output Ports",
    response_model=ApiCallOutputPortTestResponse,
)
def test_api_call_output_ports_v2(
    project_id: UUID,
    graph_runner_id: UUID,
    instance_id: UUID,
    payload: ApiCallOutputPortTestRequest,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> ApiCallOutputPortTestResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        validate_graph_runner_belongs_to_project(session, graph_runner_id, project_id)
        validate_graph_is_draft(session, graph_runner_id)
        if instance_id not in {node.id for node in get_component_nodes(session, graph_runner_id)}:
            raise ValueError(f"Component instance {instance_id} does not belong to graph {graph_runner_id}")
        output_port_names = test_and_persist_api_call_get_auto_output_ports(
            session=session,
            component_instance_id=instance_id,
            parameters=payload.parameters,
        )
    except ValueError as e:
        LOGGER.warning("Invalid API Call output-port test request for instance %s: %s", instance_id, e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    graph_mutation_helpers.record_modification_history(session, graph_runner_id, user_id=user.id)
    notify_graph_changed(project_id, graph_runner_id, "component.updated")
    return ApiCallOutputPortTestResponse(output_port_names=output_port_names)
