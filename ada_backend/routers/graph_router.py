import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import DBAPIError, DisconnectionError, IntegrityError
from sqlalchemy.orm import Session

from ada_backend.database.models import EnvType
from ada_backend.database.setup_db import get_db
from ada_backend.repositories.project_repository import get_project
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.pipeline.field_expression_schema import (
    FieldExpressionAutocompleteRequest,
    FieldExpressionAutocompleteResponse,
)
from ada_backend.schemas.pipeline.graph_schema import (
    GraphDeployResponse,
    GraphGetResponse,
    GraphLoadResponse,
    GraphModificationHistoryResponse,
    GraphSaveVersionResponse,
    GraphUpdateResponse,
    GraphUpdateSchema,
)
from ada_backend.services.graph.delete_graph_service import delete_graph_runner_service
from ada_backend.services.graph.deploy_graph_service import (
    bind_graph_to_env_service,
    deploy_graph_service,
    load_version_as_draft_service,
    save_graph_version_service,
)
from ada_backend.services.graph.field_expression_autocomplete_service import (
    autocomplete_field_expression,
)
from ada_backend.services.graph.get_graph_modification_history_service import (
    get_graph_modification_history_service,
)
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.load_copy_graph_service import load_copy_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_with_history_service

router = APIRouter(
    prefix="/projects/{project_id}/graph",
)
LOGGER = logging.getLogger(__name__)


@router.get("/{graph_runner_id}", summary="Get Project Graph", response_model=GraphGetResponse, tags=["Graph"])
def get_project_graph(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    sqlaclhemy_db_session: Session = Depends(get_db),
) -> GraphGetResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_graph_service(sqlaclhemy_db_session, project_id, graph_runner_id)
    except (DBAPIError, DisconnectionError) as e:
        LOGGER.error(
            "Database connection failed for project %s and runner %s", project_id, graph_runner_id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database connection failed, please retry") from e
    except ValueError as e:
        LOGGER.error(
            "Failed to get graph for project %s and runner %s: %s", project_id, graph_runner_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=400, detail="Failed to load graph: the graph data may be corrupted or incomplete"
        ) from e


@router.get(
    "/{graph_runner_id}/modification-history",
    summary="Get Graph Modification History",
    response_model=GraphModificationHistoryResponse,
    tags=["Graph"],
)
def get_graph_modification_history(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphModificationHistoryResponse:
    """
    Get the modification history for a graph runner.
    Returns a list of all modifications with timestamp and user_id.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_graph_modification_history_service(session, project_id, graph_runner_id)
    except (DBAPIError, DisconnectionError) as e:
        LOGGER.error(
            "Database connection failed for project %s and runner %s", project_id, graph_runner_id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database connection failed, please retry") from e
    except ValueError as e:
        LOGGER.error(
            "Failed to get modification history for project %s and runner %s: %s",
            project_id, graph_runner_id, e, exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Failed to load modification history for this graph") from e


@router.put(
    "/{graph_runner_id}", summary="Update Project Graph Runner", response_model=GraphUpdateResponse, tags=["Graph"]
)
async def update_project_pipeline(
    project_id: UUID,
    graph_runner_id: UUID,
    project_graph: GraphUpdateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphUpdateResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    project = get_project(session, project_id=project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return await update_graph_with_history_service(
            session=session,
            graph_project=project_graph,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
            user_id=user.id,
        )
    except (DBAPIError, DisconnectionError) as e:
        LOGGER.error(
            "Database connection failed for project %s runner %s", project_id, graph_runner_id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database connection failed, please retry") from e
    except ValueError as e:
        error_msg = str(e)
        LOGGER.error(
            "Failed to update graph for project %s runner %s: %s", project_id, graph_runner_id, e, exc_info=True
        )
        if "only draft versions" in error_msg.lower():
            raise HTTPException(status_code=403, detail="Only the draft version can be modified") from e
        raise HTTPException(status_code=400, detail="Invalid graph update request") from e


@router.get(
    "/{graph_runner_id}/field-expressions/autocomplete",
    summary="Autocomplete Field Expression References",
    response_model=FieldExpressionAutocompleteResponse,
    tags=["Graph"],
)
def autocomplete_field_expressions_endpoint(
    project_id: UUID,
    graph_runner_id: UUID,
    target_instance_id: UUID,
    query: str = "",
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value))
    ] = None,
    session: Session = Depends(get_db),
) -> FieldExpressionAutocompleteResponse:
    if not user or not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    # TODO: Add (DBAPIError, DisconnectionError) fallback like other endpoints in this router.
    request = FieldExpressionAutocompleteRequest(
        target_instance_id=target_instance_id,
        query=query,
    )
    return autocomplete_field_expression(session, project_id, graph_runner_id, request)


@router.post(
    "/{graph_runner_id}/deploy", summary="Deploy Graph Runner", response_model=GraphDeployResponse, tags=["Graph"]
)
def deploy_graph(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphDeployResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    project = get_project(session, project_id=project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        result = deploy_graph_service(
            session=session,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
            user_id=user.id,
            organization_id=project.organization_id,
        )
    except IntegrityError as e:
        session.rollback()
        LOGGER.error(
            "Conflict deploying graph runner %s for project %s: concurrent deployment detected",
            graph_runner_id, project_id, exc_info=True,
        )
        raise HTTPException(
            status_code=409,
            detail="Conflict: another deployment for this project's production environment is in progress",
        ) from e
    except ValueError as e:
        LOGGER.error(
            "Failed to deploy graph for project %s runner %s: %s", project_id, graph_runner_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=400,
            detail="Failed to deploy: the graph contains data that could not be cloned to production",
        ) from e

    return result


@router.post(
    "/{graph_runner_id}/save-version",
    summary="Save Version from Draft",
    response_model=GraphSaveVersionResponse,
    tags=["Graph"],
)
def save_graph_version(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphSaveVersionResponse:
    project = get_project(session, project_id=project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        result = save_graph_version_service(
            session=session,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
            user_id=user.id,
            organization_id=project.organization_id,
        )
    except (DBAPIError, DisconnectionError) as e:
        LOGGER.error(
            "Database connection failed for project %s runner %s", project_id, graph_runner_id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database connection failed, please retry") from e
    except ValueError as e:
        LOGGER.error(
            "Failed to save version for project %s runner %s: %s", project_id, graph_runner_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=400,
            detail="Failed to save version: the graph contains data that could not be cloned",
        ) from e

    return result


@router.get(
    "/{graph_runner_id}/load-copy",
    summary="Load a copy of a Project Graph to use it",
    response_model=GraphLoadResponse,
    tags=["Graph"],
)
def load_copy_graph_runner(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphLoadResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    project = get_project(session, project_id=project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return load_copy_graph_service(
            session=session,
            project_id_to_copy=project_id,
            graph_runner_id_to_copy=graph_runner_id,
        )
    except ValueError as e:
        LOGGER.error(
            "Failed to copy graph for project %s runner %s: %s", project_id, graph_runner_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=400,
            detail="Failed to copy graph: the graph contains data that could not be cloned",
        ) from e


@router.put(
    "/{graph_runner_id}/env/{env}",
    summary="Bind Graph Runner to Environment",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Graph"],
)
def bind_graph_to_env(
    project_id: UUID,
    graph_runner_id: UUID,
    env: EnvType,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    try:
        bind_graph_to_env_service(
            session=session,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
            env=env,
        )
    except IntegrityError as e:
        session.rollback()
        LOGGER.warning(
            "Conflict binding graph runner %s to %s for project %s: "
            "another graph runner was concurrently bound to this environment",
            graph_runner_id, env.value, project_id,
        )
        raise HTTPException(
            status_code=409,
            detail=f"Another graph runner was concurrently bound to {env.value} for this project. "
            "Please retry the operation.",
        ) from e


@router.post(
    "/{graph_runner_id}/load-as-draft",
    summary="Load a version as draft",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Graph"],
)
def load_version_as_draft(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    try:
        load_version_as_draft_service(
            session=session,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
        )
    except ValueError as e:
        LOGGER.error(
            "Failed to load version as draft for project %s runner %s: %s",
            project_id, graph_runner_id, e, exc_info=True,
        )
        raise HTTPException(
            status_code=400,
            detail="Failed to load version as draft: the graph contains data that could not be cloned",
        ) from e


@router.delete("/{graph_runner_id}", summary="Delete Graph Runner", tags=["Graph"])
def delete_graph_runner_endpoint(
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    delete_graph_runner_service(session, graph_runner_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
