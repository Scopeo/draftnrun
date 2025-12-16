from typing import Annotated, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
import logging

from ada_backend.database.models import EnvType, CallType, ProjectType, ResponseFormat
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.chart_schema import ChartsResponse
from ada_backend.schemas.monitor_schema import KPISResponse
from ada_backend.schemas.project_schema import (
    ChatResponse,
    ProjectDeleteResponse,
    ProjectSchema,
    ProjectWithGraphRunnersSchema,
    ProjectUpdateSchema,
    ProjectCreateSchema,
)
from ada_backend.services.agent_runner_service import run_agent, run_env_agent
from ada_backend.routers.auth_router import (
    verify_api_key_dependency,
    VerifiedApiKey,
    user_has_access_to_organization_dependency,
    user_has_access_to_project_dependency,
    UserRights,
)
from ada_backend.services.charts_service import get_charts_by_project
from ada_backend.services.errors import (
    MissingDataSourceError,
    ProjectNotFound,
    EnvironmentNotFound,
    OrganizationLimitExceededError,
)
from ada_backend.services.metrics.monitor_kpis_service import get_monitoring_kpis_by_project
from ada_backend.services.project_service import (
    create_workflow,
    delete_project_service,
    get_project_service,
    get_projects_by_organization_with_details_service,
    update_project_service,
)
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from engine.agent.errors import (
    KeyTypePromptTemplateError,
    MissingKeyPromptTemplateError,
)
from ada_backend.services.tag_service import compose_tag_name

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/projects")


@router.get("/org/{organization_id}", response_model=List[ProjectWithGraphRunnersSchema], tags=["Projects"])
def get_projects_by_organization_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(
            user_has_access_to_organization_dependency(
                allowed_roles=UserRights.MEMBER.value,
            )
        ),
    ],
    session: Session = Depends(get_db),
    type: Optional[ProjectType] = ProjectType.WORKFLOW,
    include_templates: Optional[bool] = False,
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_projects_by_organization_with_details_service(
            session, organization_id, user.id, type, include_templates
        )
    except ValueError as e:
        LOGGER.error(
            f"Failed to list workflows for organization {organization_id} and user {user.id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to list workflows for organization {organization_id} and user {user.id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


# TODO: move to workflow_router
@router.get("/{project_id}", response_model=ProjectWithGraphRunnersSchema, tags=["Workflows"])
def get_workflow_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_project_service(session, project_id)
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(f"Failed to get workflow {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get workflow {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/{project_id}", response_model=ProjectDeleteResponse, tags=["Projects"])
def delete_project_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> ProjectDeleteResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return delete_project_service(session, project_id)
    except ValueError as e:
        LOGGER.error(f"Failed to delete project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch("/{project_id}", response_model=ProjectSchema, tags=["Projects"])
def update_project_endpoint(
    project_id: UUID,
    project: ProjectUpdateSchema,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> ProjectSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return update_project_service(session, user.id, project_id, project)
    except ValueError as e:
        LOGGER.error(f"Failed to update project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to update project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# TODO: move to workflow_router
@router.post("/{organization_id}", response_model=ProjectWithGraphRunnersSchema, tags=["Workflows"])
def create_workflow_endpoint(
    organization_id: UUID,
    project: ProjectCreateSchema,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> ProjectWithGraphRunnersSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return create_workflow(session, user.id, organization_id, project)
    except ValueError as e:
        LOGGER.error(f"Failed to create workflow in organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create workflow in organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{project_id}/{env}/run", response_model=ChatResponse)
async def run_env_agent_endpoint(
    project_id: UUID,
    env: EnvType,
    input_data: dict = Body(
        ...,
        example={
            "messages": [
                {"role": "user", "content": "Hello, how are you?"},
            ]
        },
    ),
    response_format: Optional[ResponseFormat] = Query(
        None,
        description=(
            "If provided, files generated during execution are returned "
            "either as base64 or as presigned S3 URLs. "
            "Only 'base64' or 'url' are allowed for this endpoint."
        ),
    ),
    sqlaclhemy_db_session: Session = Depends(get_db),
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
) -> ChatResponse:
    if verified_api_key.project_id != project_id:
        raise HTTPException(status_code=403, detail="You don't have access to this project")

    if response_format == ResponseFormat.S3_KEY:
        raise HTTPException(
            status_code=400,
            detail="'s3_key' is not allowed for this endpoint. Only 'base64' or 'url' are supported.",
        )

    try:
        return await run_env_agent(
            session=sqlaclhemy_db_session,
            project_id=project_id,
            input_data=input_data,
            env=env,
            call_type=CallType.API,
            response_format=response_format,
        )
    except EnvironmentNotFound as e:
        LOGGER.error(f"Environment not found for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except MissingDataSourceError as e:
        LOGGER.error(f"Data source not found for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MissingKeyPromptTemplateError as e:
        LOGGER.error(
            f"Missing key from prompt template for project {project_id} in environment {env}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyTypePromptTemplateError as e:
        LOGGER.error(
            f"Key type error in prompt template for project {project_id} in environment {env}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ConnectionError as e:
        LOGGER.error(
            f"Database connection failed for project {project_id} in environment {env}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}") from e
    except ValueError as e:
        LOGGER.error(f"Failed to run agent for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}") from e
    except Exception as e:
        LOGGER.error(f"Failed to run agent for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{project_id}/charts", response_model=ChartsResponse, tags=["Metrics"])
async def get_project_charts(
    project_id: UUID,
    duration: int,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    call_type: CallType | None = None,
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        response = await get_charts_by_project(
            project_id=project_id,
            duration_days=duration,
            call_type=call_type,
        )
        return response
    except ValueError as e:
        LOGGER.error(
            f"Failed to get charts for project {project_id} with duration {duration}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get charts for project {project_id} with duration {duration}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{project_id}/kpis", response_model=KPISResponse, tags=["Metrics"])
async def get_project_monitoring_kpi(
    project_id: UUID,
    duration: int,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    call_type: CallType | None = None,
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        response = get_monitoring_kpis_by_project(user.id, project_id, duration, call_type)
        return response
    except ValueError as e:
        LOGGER.error(f"Failed to get KPIs for project {project_id} with duration {duration}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get KPIs for project {project_id} with duration {duration}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{project_id}/graphs/{graph_runner_id}/chat", response_model=ChatResponse, tags=["Projects"])
async def chat(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(
            user_has_access_to_project_dependency(
                allowed_roles=UserRights.MEMBER.value,
            )
        ),
    ],
    input_data: dict = Body(
        ...,
        example={
            "messages": [
                {"role": "user", "content": "Hello, how are you?"},
            ]
        },
    ),
    session: Session = Depends(get_db),
) -> ChatResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        # Get the environment for this graph runner
        project_env_binding = get_env_relationship_by_graph_runner_id(session, graph_runner_id)
        if not project_env_binding:
            LOGGER.error(f"Graph runner {graph_runner_id} is not bound to any project for project {project_id}")
            raise HTTPException(status_code=404, detail=f"Graph runner {graph_runner_id} is not bound to any project")
        environment = project_env_binding.environment
        LOGGER.info(f"Determined environment {environment} for graph_runner_id {graph_runner_id}")
        return await run_agent(
            session=session,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
            input_data=input_data,
            environment=environment,
            call_type=CallType.SANDBOX,
            tag_name=compose_tag_name(
                project_env_binding.graph_runner.tag_version,
                project_env_binding.graph_runner.version_name,
            ),
            response_format=ResponseFormat.S3_KEY,
        )
    except OrganizationLimitExceededError as e:
        LOGGER.warning(
            f"Organization limit exceeded for project {project_id}, graph runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=402, detail=str(e)) from e
    except MissingDataSourceError as e:
        LOGGER.error(
            f"Data source not found for project {project_id} for graph runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MissingKeyPromptTemplateError as e:
        LOGGER.error(
            f"Missing key from prompt template for project {project_id} for graph runner "
            f"{graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyTypePromptTemplateError as e:
        LOGGER.error(
            f"Key type error in prompt template for project {project_id} for graph runner "
            f"{graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ConnectionError as e:
        LOGGER.error(
            f"Database connection failed for project {project_id}, graph_runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}") from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to run agent chat for project {project_id}, graph_runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to run agent chat for project {project_id}, graph_runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{project_id}/{env}/chat", response_model=ChatResponse, tags=["Projects"])
async def chat_env(
    project_id: UUID,
    env: EnvType,
    user: Annotated[
        SupabaseUser,
        Depends(
            user_has_access_to_project_dependency(
                allowed_roles=UserRights.MEMBER.value,
            )
        ),
    ],
    input_data: dict = Body(
        ...,
        example={
            "messages": [
                {"role": "user", "content": "Hello, how are you?"},
            ]
        },
    ),
    session: Session = Depends(get_db),
) -> ChatResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return await run_env_agent(
            session=session,
            project_id=project_id,
            input_data=input_data,
            env=env,
            call_type=CallType.SANDBOX,
            response_format=ResponseFormat.S3_KEY,
        )
    except OrganizationLimitExceededError as e:
        LOGGER.warning(
            f"Organization limit exceeded for project {project_id} in environment {env}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=402, detail=str(e)) from e
    except EnvironmentNotFound as e:
        LOGGER.error(f"Environment not found for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except MissingDataSourceError as e:
        LOGGER.error(f"Data source not found for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MissingKeyPromptTemplateError as e:
        LOGGER.error(
            f"Missing key from prompt template for project {project_id} in environment " f"{env}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyTypePromptTemplateError as e:
        LOGGER.error(
            f"Key type error in prompt template for project {project_id} in environment " f"{env}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e

    except ConnectionError as e:
        LOGGER.error(
            f"Database connection failed for project {project_id} in environment {env}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}") from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to run agent chat for project {project_id} in environment {env}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to run agent chat for project {project_id} in environment {env}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e
