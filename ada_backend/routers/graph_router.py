from typing import Annotated
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
    GraphLoadResponse,
    GraphModificationHistoryResponse,
    GraphUpdateResponse,
    GraphUpdateSchema,
)
from ada_backend.database.setup_db import get_db

from ada_backend.services.errors import GraphNotFound, MissingDataSourceError, ProjectNotFound
from ada_backend.services.graph.deploy_graph_service import deploy_graph_service
from ada_backend.services.graph.load_copy_graph_service import load_copy_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_with_history_service
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.get_graph_modification_history_service import (
    get_graph_modification_history_service,
)
from ada_backend.services.graph.delete_graph_service import delete_graph_runner_service
from engine.field_expressions.errors import FieldExpressionError
from engine.agent.errors import (
    KeyTypePromptTemplateError,
    MissingKeyPromptTemplateError,
)

router = APIRouter(
    prefix="/projects/{project_id}/graph",
)
LOGGER = logging.getLogger(__name__)


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
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except GraphNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConnectionError as e:
        LOGGER.error(
            f"Database connection failed for project {project_id} and runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}") from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to get graph for project {project_id} and runner {graph_runner_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get graph for project {project_id} and runner {graph_runner_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value))
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
    except (ProjectNotFound, GraphNotFound) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConnectionError as e:
        LOGGER.error(
            f"Database connection failed for project {project_id} and runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}") from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to get modification history for project {project_id} and runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get modification history for project {project_id} and runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
        return await update_graph_with_history_service(
            session=session,
            graph_project=project_graph,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
            user_id=user.id,
        )
    except ConnectionError as e:
        LOGGER.error(
            f"Database connection failed for project {project_id} runner {graph_runner_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}") from e
    except FieldExpressionError as e:
        error_msg = str(e)
        LOGGER.error(
            f"Failed to update graph for project {project_id} runner {graph_runner_id}: {error_msg}", exc_info=True
        )
        raise HTTPException(status_code=400, detail=error_msg) from e
    except MissingDataSourceError as e:
        LOGGER.warning(
            f"Graph saved with missing data source for project {project_id} runner {graph_runner_id}: {str(e)}"
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MissingKeyPromptTemplateError as e:
        LOGGER.error(
            f"Missing key from prompt template for project {project_id} runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyTypePromptTemplateError as e:
        LOGGER.error(
            f"Key type error in prompt template for project {project_id} runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        error_msg = str(e)
        LOGGER.error(
            f"Failed to update graph for project {project_id} runner {graph_runner_id}: {error_msg}", exc_info=True
        )
        # Check if this is a draft mode validation error
        if "only draft versions" in error_msg.lower():
            raise HTTPException(status_code=403, detail="Only the draft version can be modified") from e
        raise HTTPException(status_code=400, detail=f"Error: {error_msg}") from e


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
    except FieldExpressionError as e:
        error_msg = str(e)
        LOGGER.error(
            f"Failed to deploy graph for project {project_id} runner {graph_runner_id}: {error_msg}", exc_info=True
        )
        raise HTTPException(status_code=400, detail=error_msg) from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to deploy graph for project {project_id} runner {graph_runner_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e


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
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value))
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
    except FieldExpressionError as e:
        error_msg = str(e)
        LOGGER.error(
            f"Failed to load copy of graph for project {project_id} runner {graph_runner_id}: {error_msg}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=error_msg) from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to load copy of graph for project {project_id} runner {graph_runner_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e


@router.delete("/{graph_runner_id}", summary="Delete Graph Runner", tags=["Graph"])
def delete_graph_runner_endpoint(
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
):
    """
    Delete a graph runner and everything related to it.
    This includes all components, edges, and the graph runner itself.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        delete_graph_runner_service(session, graph_runner_id)
    except Exception as e:
        LOGGER.error(f"Failed to delete graph runner {graph_runner_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from e

    return Response(status_code=status.HTTP_204_NO_CONTENT)
