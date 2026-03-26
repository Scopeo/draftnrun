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
from ada_backend.services.errors import (
    GraphConflictError,
    GraphNotBoundToProjectError,
    GraphNotFound,
    GraphRunnerAlreadyInEnvironmentError,
    GraphVersionSavingFromNonDraftError,
    MissingDataSourceError,
    MissingIntegrationError,
    ProjectNotFound,
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
from engine.components.errors import (
    KeyTypePromptTemplateError,
    MCPConnectionError,
    MissingKeyPromptTemplateError,
)
from engine.field_expressions.errors import FieldExpressionError

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
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    except GraphNotFound:
        raise HTTPException(status_code=404, detail=f"Graph runner {graph_runner_id} not found")
    except GraphNotBoundToProjectError:
        raise HTTPException(
            status_code=403, detail=f"Graph runner {graph_runner_id} does not belong to project {project_id}"
        )
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
    except Exception as e:
        LOGGER.error(
            "Failed to get graph for project %s and runner %s: %s", project_id, graph_runner_id, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Unexpected error while loading the graph") from e


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
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    except GraphNotFound:
        raise HTTPException(status_code=404, detail=f"Graph runner {graph_runner_id} not found")
    except GraphNotBoundToProjectError:
        raise HTTPException(
            status_code=403, detail=f"Graph runner {graph_runner_id} does not belong to project {project_id}"
        )
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
    except Exception as e:
        LOGGER.error(
            "Failed to get modification history for project %s and runner %s: %s",
            project_id, graph_runner_id, e, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Unexpected error while loading modification history") from e


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
    except GraphConflictError:
        raise HTTPException(
            status_code=409,
            detail="The graph was modified by another client since your last fetch. Refresh the graph and retry.",
        )
    except GraphNotBoundToProjectError:
        LOGGER.warning(
            "Graph runner %s is not bound to project %s when updating graph", graph_runner_id, project_id,
        )
        raise HTTPException(
            status_code=403, detail=f"Graph runner {graph_runner_id} does not belong to project {project_id}"
        )
    except (DBAPIError, DisconnectionError) as e:
        LOGGER.error(
            "Database connection failed for project %s runner %s", project_id, graph_runner_id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database connection failed, please retry") from e
    except FieldExpressionError as e:
        LOGGER.warning(
            "Invalid field expression for project %s runner %s: %s", project_id, graph_runner_id, e
        )
        raise HTTPException(status_code=400, detail="Invalid field expression in the graph configuration") from e
    except MissingDataSourceError as e:
        LOGGER.warning(
            "Graph saved with missing data source for project %s runner %s: %s", project_id, graph_runner_id, e
        )
        detail = (
            f"Component '{e.component_name}' requires a data source to be configured"
            if e.component_name
            else "A component in the graph requires a data source to be configured"
        )
        raise HTTPException(status_code=400, detail=detail) from e
    except MissingKeyPromptTemplateError as e:
        LOGGER.warning(
            "Missing key from prompt template for project %s runner %s: %s", project_id, graph_runner_id, e,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Missing template variable(s) in prompt: {', '.join(e.missing_keys)}",
        ) from e
    except KeyTypePromptTemplateError as e:
        LOGGER.warning(
            "Key type error in prompt template for project %s runner %s: %s", project_id, graph_runner_id, e,
        )
        raise HTTPException(
            status_code=400, detail=f"Template variable '{e.key}' has an incompatible value type"
        ) from e
    except MCPConnectionError as e:
        LOGGER.warning(
            "MCP connection failed for project %s runner %s: %s", project_id, graph_runner_id, e,
        )
        raise HTTPException(
            status_code=400, detail="An MCP tool in the graph failed to connect to its endpoint"
        ) from e
    except MissingIntegrationError as e:
        LOGGER.warning(
            "Missing integration for project %s runner %s: %s", project_id, graph_runner_id, e
        )
        raise HTTPException(
            status_code=400,
            detail=f"Component '{e.component_instance_name}' requires the "
            f"'{e.integration_name}' integration to be connected",
        ) from e
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
    try:
        request = FieldExpressionAutocompleteRequest(
            target_instance_id=target_instance_id,
            query=query,
        )
        return autocomplete_field_expression(session, project_id, graph_runner_id, request)
    except GraphNotFound:
        raise HTTPException(status_code=404, detail=f"Graph runner {graph_runner_id} not found")
    except GraphNotBoundToProjectError:
        raise HTTPException(
            status_code=403, detail=f"Graph runner {graph_runner_id} does not belong to project {project_id}"
        )
    except Exception as e:
        LOGGER.error(
            "Failed to autocomplete field expressions for project %s runner %s: %s",
            project_id, graph_runner_id, e, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Unexpected error during field expression autocomplete") from e


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
    except GraphNotFound:
        LOGGER.warning(
            "Graph runner %s not found when deploying to production for project %s",
            graph_runner_id, project_id,
        )
        raise HTTPException(status_code=404, detail=f"Graph runner {graph_runner_id} not found")
    except GraphNotBoundToProjectError:
        LOGGER.warning(
            "Graph runner %s is not bound to project %s when deploying to production",
            graph_runner_id, project_id,
        )
        raise HTTPException(
            status_code=403, detail=f"Graph runner {graph_runner_id} does not belong to project {project_id}"
        )
    except GraphRunnerAlreadyInEnvironmentError:
        LOGGER.warning(
            "Graph runner %s is already in production for project %s", graph_runner_id, project_id,
        )
        raise HTTPException(
            status_code=400, detail=f"Graph runner {graph_runner_id} is already in production"
        )
    except FieldExpressionError as e:
        LOGGER.warning(
            "Invalid field expression when deploying project %s runner %s: %s",
            project_id, graph_runner_id, e,
        )
        raise HTTPException(
            status_code=400, detail="Cannot deploy: the graph contains an invalid field expression"
        ) from e
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
    except GraphNotFound:
        raise HTTPException(status_code=404, detail=f"Graph runner {graph_runner_id} not found")
    except GraphNotBoundToProjectError:
        raise HTTPException(
            status_code=403, detail=f"Graph runner {graph_runner_id} does not belong to project {project_id}"
        )
    except GraphVersionSavingFromNonDraftError:
        LOGGER.warning(
            "Attempted to save version from non-draft graph runner for project %s runner %s",
            project_id, graph_runner_id,
        )
        raise HTTPException(
            status_code=400, detail="Versions can only be saved from the draft environment"
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
    except Exception as e:
        LOGGER.error(
            "Failed to save version for project %s runner %s: %s", project_id, graph_runner_id, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Unexpected error while saving graph version") from e

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
    except FieldExpressionError as e:
        LOGGER.error(
            "Invalid field expression when copying graph for project %s runner %s: %s",
            project_id, graph_runner_id, e, exc_info=True,
        )
        raise HTTPException(
            status_code=400, detail="Cannot copy graph: it contains an invalid field expression"
        ) from e
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
    except GraphNotFound:
        LOGGER.warning(
            "Graph runner %s not found when binding to %s for project %s",
            graph_runner_id, env.value, project_id,
        )
        raise HTTPException(status_code=404, detail=f"Graph runner {graph_runner_id} not found")
    except GraphNotBoundToProjectError:
        LOGGER.warning(
            "Graph runner %s is not bound to project %s when binding to %s",
            graph_runner_id, project_id, env.value,
        )
        raise HTTPException(
            status_code=403, detail=f"Graph runner {graph_runner_id} does not belong to project {project_id}"
        )
    except GraphRunnerAlreadyInEnvironmentError:
        LOGGER.warning(
            "Graph runner %s is already in %s for project %s",
            graph_runner_id, env.value, project_id,
        )
        raise HTTPException(
            status_code=400, detail=f"Graph runner {graph_runner_id} is already in {env.value}"
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
    except Exception as e:
        LOGGER.error(
            "Unexpected error binding graph runner %s to %s for project %s",
            graph_runner_id, env.value, project_id, exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Unexpected error while binding graph runner to environment"
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
    except GraphNotFound:
        LOGGER.warning(
            "Graph runner %s not found when loading as draft for project %s",
            graph_runner_id, project_id,
        )
        raise HTTPException(status_code=404, detail=f"Graph runner {graph_runner_id} not found")
    except GraphNotBoundToProjectError:
        LOGGER.warning(
            "Graph runner %s is not bound to project %s when loading as draft",
            graph_runner_id, project_id,
        )
        raise HTTPException(
            status_code=403, detail=f"Graph runner {graph_runner_id} does not belong to project {project_id}"
        )
    except GraphRunnerAlreadyInEnvironmentError:
        LOGGER.warning(
            "Graph runner %s is already in draft for project %s", graph_runner_id, project_id,
        )
        raise HTTPException(
            status_code=400, detail=f"Graph runner {graph_runner_id} is already in draft"
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
    except Exception as e:
        LOGGER.error(
            "Unexpected error loading version as draft for project %s runner %s",
            project_id, graph_runner_id, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Unexpected error while loading version as draft") from e


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
    try:
        delete_graph_runner_service(session, graph_runner_id)
    except Exception as e:
        LOGGER.error("Failed to delete graph runner %s", graph_runner_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error while deleting graph runner") from e

    return Response(status_code=status.HTTP_204_NO_CONTENT)
