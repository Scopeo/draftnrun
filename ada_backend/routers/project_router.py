from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
import logging

from ada_backend.database.models import EnvType, CallType
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.chart_schema import ChartsResponse
from ada_backend.schemas.monitor_schema import KPISResponse
from ada_backend.schemas.project_schema import (
    ChatResponse,
    ProjectDeleteResponse,
    ProjectResponse,
    ProjectSchema,
    ProjectWithGraphRunnersSchema,
    ProjectUpdateSchema,
    ProjectCreateSchema,
)
from ada_backend.services.agent_runner_service import run_agent, run_env_agent
from ada_backend.routers.auth_router import (
    get_user_from_supabase_token,
    verify_api_key_dependency,
    VerifiedApiKey,
    user_has_access_to_organization_dependency,
    user_has_access_to_project_dependency,
    UserRights,
)
from ada_backend.services.charts_service import get_charts_by_project
from ada_backend.services.errors import ProjectNotFound, EnvironmentNotFound
from ada_backend.services.metrics.monitor_kpis_service import get_monitoring_kpis_by_project
from ada_backend.services.project_service import (
    create_workflow,
    delete_project_service,
    get_project_service,
    get_workflows_by_organization_service,
    update_project_service,
)
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id

LOGGER = logging.getLogger(__name__)


router = APIRouter(prefix="/projects")


# TODO: move to workflow_router
@router.get("/org/{organization_id}", response_model=List[ProjectResponse], tags=["Workflows"])
def get_workflows_by_organization_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(
            user_has_access_to_organization_dependency(
                allowed_roles=UserRights.USER.value,
            )
        ),
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_workflows_by_organization_service(session, organization_id, user.id)
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.ADMIN.value)),
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.ADMIN.value)),
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
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value)),
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
    sqlaclhemy_db_session: Session = Depends(get_db),
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
) -> ChatResponse:
    if verified_api_key.project_id != project_id:
        raise HTTPException(status_code=403, detail="You don't have access to this project")
    try:
        return await run_env_agent(
            session=sqlaclhemy_db_session,
            project_id=project_id,
            input_data=input_data,
            env=env,
            call_type=CallType.API,
        )
    except EnvironmentNotFound as e:
        LOGGER.error(f"Environment not found for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(f"Failed to run agent for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to run agent for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{project_id}/charts", response_model=ChartsResponse, tags=["Metrics"])
async def get_project_charts(
    project_id: UUID,
    duration: int,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    call_type: CallType | None = None,
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        response = await get_charts_by_project(project_id, duration, call_type)
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
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
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
                allowed_roles=UserRights.USER.value,
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
        environment = project_env_binding.environment
        LOGGER.info(f"Determined environment {environment} for graph_runner_id {graph_runner_id}")
        return await run_agent(
            session=session,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
            input_data=input_data,
            environment=environment,
            call_type=CallType.SANDBOX,
            tag_version=project_env_binding.graph_runner.tag_version,
        )
    except ValueError as e:
        LOGGER.error(
            f"Failed to run agent chat for project {project_id}, graph_runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
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
                allowed_roles=UserRights.USER.value,
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
        )
    except EnvironmentNotFound as e:
        LOGGER.error(f"Environment not found for project {project_id} in environment {env}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to run agent chat for project {project_id} in environment {env}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to run agent chat for project {project_id} in environment {env}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{project_id}/sync-cron-payload", tags=["Projects"])
def sync_cron_payload(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(
            user_has_access_to_project_dependency(
                allowed_roles=UserRights.WRITER.value,
            )
        ),
    ],
    session: Session = Depends(get_db),
):
    """
    Update cron job's input_data payload from the Start node's payload schema defaults.

    Extracts default values from the draft version's Start node payload schema
    and updates the cron job accordingly.
    """
    from ada_backend.repositories.project_repository import get_project_with_details
    from ada_backend.repositories.graph_runner_repository import get_component_nodes
    from ada_backend.repositories.component_repository import get_component_instance_by_id
    from ada_backend.repositories.cron_repository import get_cron_jobs_by_organization
    from ada_backend.services.cron.service import update_cron_job_service
    from ada_backend.schemas.cron_schema import CronJobUpdate
    import json

    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        # Get project
        project = get_project_with_details(session, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Find draft graph runner (always use draft for schema extraction, same as before)
        draft_graph_runner = None
        for gr in project.graph_runners:
            if gr.env == "draft" and gr.tag_version is None:
                draft_graph_runner = gr
                break

        if not draft_graph_runner:
            return {"status": "no_draft", "message": "No draft version found"}

        # Get Start nodes from draft
        component_nodes = get_component_nodes(session, draft_graph_runner.graph_runner_id)
        start_nodes = [cn for cn in component_nodes if cn.is_start_node]

        if not start_nodes:
            return {"status": "no_start_node", "message": "No Start node found"}

        # Get payload schema from first Start node
        start_node = start_nodes[0]
        component_instance = get_component_instance_by_id(session, start_node.component_instance_id)

        if not component_instance:
            raise HTTPException(status_code=404, detail="Start node component instance not found")

        # Extract payload schema
        payload_schema_value = None
        for param in component_instance.basic_parameters:
            if param.parameter_definition.name == "payload_schema":
                payload_schema_value = param.value
                break

        if not payload_schema_value:
            return {"status": "no_schema", "message": "No payload schema found in Start node"}

        # Extract default values from schema (same logic that worked before)
        cron_payload = {}
        if payload_schema_value:
            try:
                schema = json.loads(payload_schema_value)
                if isinstance(schema, dict) and "default" in schema:
                    cron_payload = schema["default"]
                elif isinstance(schema, dict) and "properties" in schema:
                    cron_payload = {}
                    for prop_name, prop_schema in schema["properties"].items():
                        if isinstance(prop_schema, dict) and "default" in prop_schema:
                            cron_payload[prop_name] = prop_schema["default"]
            except (json.JSONDecodeError, ValueError, KeyError):
                pass

        # Find cron job for this project
        cron_jobs = get_cron_jobs_by_organization(session, project.organization_id, enabled_only=False)
        project_cron = None
        for job in cron_jobs:
            if job.payload and job.payload.get("project_id") == str(project_id):
                project_cron = job
                break

        if not project_cron:
            return {"status": "no_cron", "message": "No cron job found for this project"}

        # Update cron job's input_data
        updated_payload = project_cron.payload.copy()
        updated_payload["input_data"] = cron_payload

        update_data = CronJobUpdate(payload=updated_payload)
        update_cron_job_service(
            session,
            project_cron.id,
            update_data,
            project.organization_id,
            user_id=user.id,
        )

        return {
            "status": "success",
            "message": "Cron payload synced from Start node schema",
            "cron_id": str(project_cron.id),
            "input_data": cron_payload,
        }
    except Exception as e:
        LOGGER.error(f"Failed to sync cron payload for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
