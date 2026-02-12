import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, EnvType, ProjectType, ResponseFormat
from ada_backend.database.setup_db import get_db
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.repositories.project_repository import get_project
from ada_backend.repositories import variable_definitions_repository
from ada_backend.repositories import variable_sets_repository
from ada_backend.routers.auth_router import (
    UserRights,
    VerifiedApiKey,
    user_has_access_to_organization_dependency,
    user_has_access_to_organization_xor_verify_api_key,
    user_has_access_to_project_dependency,
    verify_api_key_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.chart_schema import ChartsResponse
from ada_backend.schemas.monitor_schema import KPISResponse
from ada_backend.schemas.project_schema import (
    ChatResponse,
    ProjectCreateSchema,
    ProjectDeleteResponse,
    ProjectSchema,
    ProjectUpdateSchema,
    ProjectWithGraphRunnersSchema,
)
from ada_backend.schemas.variable_schemas import (
    VariableDefinitionBulkUpsertRequest,
    VariableDefinitionResponse,
    VariableDefinitionUpsertRequest,
    VariableSetListResponse,
    VariableSetResponse,
    VariableSetUpsertRequest,
)
from ada_backend.services.agent_runner_service import run_agent, run_env_agent
from ada_backend.services.variable_resolution_service import resolve_variables
from ada_backend.services.charts_service import get_charts_by_project
from ada_backend.services.errors import (
    EnvironmentNotFound,
    MissingDataSourceError,
    MissingIntegrationError,
    OrganizationLimitExceededError,
    ProjectNotFound,
)
from ada_backend.services.metrics.monitor_kpis_service import get_monitoring_kpis_by_project
from ada_backend.services.project_service import (
    create_workflow,
    delete_project_service,
    get_project_service,
    get_projects_by_organization_with_details_service,
    update_project_service,
)
from ada_backend.services.tag_service import compose_tag_name
from engine.components.errors import (
    KeyTypePromptTemplateError,
    MissingKeyPromptTemplateError,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/projects")


@router.get("/org/{organization_id}", response_model=List[ProjectWithGraphRunnersSchema], tags=["Projects"])
def get_projects_by_organization_endpoint(
    organization_id: UUID,
    auth: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(
            user_has_access_to_organization_xor_verify_api_key(
                allowed_roles=UserRights.MEMBER.value,
            )
        ),
    ],
    session: Session = Depends(get_db),
    type: Optional[ProjectType] = ProjectType.WORKFLOW,
    include_templates: Optional[bool] = False,
):
    user_id, _ = auth
    try:
        return get_projects_by_organization_with_details_service(
            session, organization_id, user_id, type, include_templates
        )
    except ValueError as e:
        LOGGER.error(
            f"Failed to list workflows for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to list workflows for organization {organization_id}: {str(e)}", exc_info=True
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

    # Variable resolution: support both set_id (string, backward compat) and set_ids (list)
    set_id = input_data.pop("set_id", None)
    set_ids = input_data.pop("set_ids", None)

    resolved_variables = None
    if set_id or set_ids:
        project = get_project(sqlaclhemy_db_session, project_id=project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        ids = set_ids if set_ids else [set_id]
        resolved_variables = await resolve_variables(
            sqlaclhemy_db_session, project_id, project.organization_id, ids
        )

    try:
        return await run_env_agent(
            session=sqlaclhemy_db_session,
            project_id=project_id,
            input_data=input_data,
            env=env,
            call_type=CallType.API,
            response_format=response_format,
            variables=resolved_variables,
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
    except MissingIntegrationError as e:
        LOGGER.error(f"Missing integration for project {project_id} in environment {env}: {str(e)}", exc_info=True)
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
            f"Missing key from prompt template for project {project_id} for graph runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyTypePromptTemplateError as e:
        LOGGER.error(
            f"Key type error in prompt template for project {project_id} for graph runner {graph_runner_id}: {str(e)}",
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
            f"Missing key from prompt template for project {project_id} in environment {env}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyTypePromptTemplateError as e:
        LOGGER.error(
            f"Key type error in prompt template for project {project_id} in environment {env}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MissingIntegrationError as e:
        LOGGER.error(f"Missing integration for project {project_id} in environment {env}: {str(e)}", exc_info=True)
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


# --- Variable Definition Endpoints ---


def _definition_to_response(d) -> VariableDefinitionResponse:
    return VariableDefinitionResponse(
        id=d.id,
        organization_id=d.organization_id,
        project_id=d.project_id,
        name=d.name,
        type=d.type,
        description=d.description,
        required=d.required,
        default_value=d.default_value,
        metadata=d.variable_metadata,
        editable=d.editable,
        display_order=d.display_order,
        created_at=str(d.created_at),
        updated_at=str(d.updated_at),
    )


@router.get(
    "/{project_id}/variable-definitions",
    response_model=List[VariableDefinitionResponse],
    tags=["Variable Definitions"],
)
def list_variable_definitions_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        defs = variable_definitions_repository.list_definitions(session, project_id)
        return [_definition_to_response(d) for d in defs]
    except Exception as e:
        LOGGER.error(f"Failed to list variable definitions for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/{project_id}/variable-definitions/{name}",
    response_model=VariableDefinitionResponse,
    tags=["Variable Definitions"],
)
def get_variable_definition_endpoint(
    project_id: UUID,
    name: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        d = variable_definitions_repository.get_definition(session, project_id, name)
        if not d:
            raise HTTPException(status_code=404, detail=f"Variable definition '{name}' not found")
        return _definition_to_response(d)
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to get variable definition {name} for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put(
    "/{project_id}/variable-definitions/{name}",
    response_model=VariableDefinitionResponse,
    tags=["Variable Definitions"],
)
def upsert_variable_definition_endpoint(
    project_id: UUID,
    name: str,
    body: VariableDefinitionUpsertRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        fields = body.model_dump(exclude_none=True)
        d = variable_definitions_repository.upsert_definition(session, project_id, name, **fields)
        return _definition_to_response(d)
    except ValueError as e:
        LOGGER.error(f"Failed to upsert variable definition {name} for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to upsert variable definition {name} for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put(
    "/{project_id}/variable-definitions",
    response_model=List[VariableDefinitionResponse],
    tags=["Variable Definitions"],
)
def bulk_upsert_variable_definitions_endpoint(
    project_id: UUID,
    body: VariableDefinitionBulkUpsertRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        defs = variable_definitions_repository.bulk_upsert_definitions(session, project_id, body.definitions)
        return [_definition_to_response(d) for d in defs]
    except ValueError as e:
        LOGGER.error(
            f"Failed to bulk upsert variable definitions for project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to bulk upsert variable definitions for project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/{project_id}/variable-definitions/{name}",
    tags=["Variable Definitions"],
)
def delete_variable_definition_endpoint(
    project_id: UUID,
    name: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        deleted = variable_definitions_repository.delete_definition(session, project_id, name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Variable definition '{name}' not found")
        return {"detail": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to delete variable definition {name} for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# --- JWT-Auth'd Variable Definition Endpoints (org-level, for Scopeo dashboard) ---


@router.get(
    "/org/{organization_id}/variable-definitions",
    response_model=List[VariableDefinitionResponse],
    tags=["Variable Definitions"],
)
def list_org_variable_definitions_jwt(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        defs = variable_definitions_repository.list_org_definitions(session, organization_id)
        return [_definition_to_response(d) for d in defs]
    except Exception as e:
        LOGGER.error(f"Failed to list variable definitions for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put(
    "/org/{organization_id}/variable-definitions/{name}",
    response_model=VariableDefinitionResponse,
    tags=["Variable Definitions"],
)
def upsert_org_variable_definition_jwt(
    organization_id: UUID,
    name: str,
    body: VariableDefinitionUpsertRequest,
    project_id: Optional[UUID] = Query(None),
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ] = None,
    session: Session = Depends(get_db),
):
    try:
        fields = body.model_dump(exclude_none=True)
        d = variable_definitions_repository.upsert_org_definition(
            session, organization_id, name, project_id=project_id, **fields
        )
        return _definition_to_response(d)
    except ValueError as e:
        LOGGER.error(f"Failed to upsert variable definition {name} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to upsert variable definition {name} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/org/{organization_id}/variable-definitions/{name}",
    tags=["Variable Definitions"],
)
def delete_org_variable_definition_jwt(
    organization_id: UUID,
    name: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        deleted = variable_definitions_repository.delete_org_definition(session, organization_id, name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Variable definition '{name}' not found")
        return {"detail": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to delete variable definition {name} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# --- JWT-Auth'd Variable Set Endpoints (for Scopeo dashboard) ---


@router.get(
    "/org/{organization_id}/variable-sets",
    response_model=VariableSetListResponse,
    tags=["Variable Sets"],
)
def list_variable_sets_jwt(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        sets = variable_sets_repository.list_org_variable_sets(session, organization_id)
        return VariableSetListResponse(variable_sets=[_set_to_response(s) for s in sets])
    except Exception as e:
        LOGGER.error(f"Failed to list variable sets for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/org/{organization_id}/variable-sets/{set_id}",
    response_model=VariableSetResponse,
    tags=["Variable Sets"],
)
def get_variable_set_jwt(
    organization_id: UUID,
    set_id: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        s = variable_sets_repository.get_org_variable_set(session, organization_id, set_id)
        if not s:
            raise HTTPException(status_code=404, detail=f"Variable set '{set_id}' not found")
        return _set_to_response(s)
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to get variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put(
    "/org/{organization_id}/variable-sets/{set_id}",
    response_model=VariableSetResponse,
    tags=["Variable Sets"],
)
def upsert_variable_set_jwt(
    organization_id: UUID,
    set_id: str,
    body: VariableSetUpsertRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        s = variable_sets_repository.upsert_org_variable_set(session, organization_id, set_id, body.values)
        return _set_to_response(s)
    except ValueError as e:
        LOGGER.error(f"Failed to upsert variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to upsert variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/org/{organization_id}/variable-sets/{set_id}",
    tags=["Variable Sets"],
)
def delete_variable_set_jwt(
    organization_id: UUID,
    set_id: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    try:
        deleted = variable_sets_repository.delete_org_variable_set(session, organization_id, set_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Variable set '{set_id}' not found")
        return {"detail": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to delete variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# --- Org-Level Variable Set Endpoints (API Key auth) ---

org_router = APIRouter(prefix="/org")


def _verify_org_access(organization_id: UUID, verified_api_key: VerifiedApiKey):
    if verified_api_key.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="You don't have access to this organization")
    if verified_api_key.scope_type != "organization":
        raise HTTPException(status_code=403, detail="Project-scoped API keys cannot access org-level resources")


def _set_to_response(s) -> VariableSetResponse:
    return VariableSetResponse(
        id=s.id,
        organization_id=s.organization_id,
        project_id=s.project_id,
        set_id=s.set_id,
        values=s.values,
        created_at=str(s.created_at),
        updated_at=str(s.updated_at),
    )


@org_router.get(
    "/{organization_id}/variable-definitions",
    response_model=List[VariableDefinitionResponse],
    tags=["Variable Definitions"],
)
def list_org_variable_definitions_api_key(
    organization_id: UUID,
    session: Session = Depends(get_db),
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
):
    _verify_org_access(organization_id, verified_api_key)
    defs = variable_definitions_repository.list_org_definitions(session, organization_id)
    return [_definition_to_response(d) for d in defs]


@org_router.get(
    "/{organization_id}/variable-sets",
    response_model=VariableSetListResponse,
    tags=["Variable Sets"],
)
def list_org_variable_sets_endpoint(
    organization_id: UUID,
    session: Session = Depends(get_db),
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
):
    _verify_org_access(organization_id, verified_api_key)
    try:
        sets = variable_sets_repository.list_org_variable_sets(session, organization_id)
        return VariableSetListResponse(variable_sets=[_set_to_response(s) for s in sets])
    except Exception as e:
        LOGGER.error(f"Failed to list variable sets for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@org_router.get(
    "/{organization_id}/variable-sets/{set_id}",
    response_model=VariableSetResponse,
    tags=["Variable Sets"],
)
def get_org_variable_set_endpoint(
    organization_id: UUID,
    set_id: str,
    session: Session = Depends(get_db),
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
):
    _verify_org_access(organization_id, verified_api_key)
    try:
        s = variable_sets_repository.get_org_variable_set(session, organization_id, set_id)
        if not s:
            raise HTTPException(status_code=404, detail=f"Variable set '{set_id}' not found")
        return _set_to_response(s)
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to get variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@org_router.put(
    "/{organization_id}/variable-sets/{set_id}",
    response_model=VariableSetResponse,
    tags=["Variable Sets"],
)
def upsert_org_variable_set_endpoint(
    organization_id: UUID,
    set_id: str,
    body: VariableSetUpsertRequest,
    session: Session = Depends(get_db),
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
):
    _verify_org_access(organization_id, verified_api_key)
    try:
        s = variable_sets_repository.upsert_org_variable_set(session, organization_id, set_id, body.values)
        return _set_to_response(s)
    except ValueError as e:
        LOGGER.error(f"Failed to upsert variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to upsert variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@org_router.delete(
    "/{organization_id}/variable-sets/{set_id}",
    tags=["Variable Sets"],
)
def delete_org_variable_set_endpoint(
    organization_id: UUID,
    set_id: str,
    session: Session = Depends(get_db),
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
):
    _verify_org_access(organization_id, verified_api_key)
    try:
        deleted = variable_sets_repository.delete_org_variable_set(session, organization_id, set_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Variable set '{set_id}' not found")
        return {"detail": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to delete variable set {set_id} for org {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
