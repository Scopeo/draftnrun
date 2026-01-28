import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.agent_schema import (
    AgentInfoSchema,
    AgentUpdateSchema,
    AgentWithGraphRunnersSchema,
    ProjectAgentSchema,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateResponse
from ada_backend.schemas.project_schema import ProjectWithGraphRunnersSchema
from ada_backend.services.agents_service import (
    create_new_agent_service,
    get_agent_by_id_service,
    get_all_agents_service,
    update_agent_service,
)
from ada_backend.services.errors import (
    GraphNotBoundToProjectError,
    GraphNotFound,
    InvalidAgentTemplate,
    MissingDataSourceError,
    MissingIntegrationError,
    ProjectNotFound,
)
from engine.components.errors import MCPConnectionError, MissingKeyPromptTemplateError
from engine.field_expressions.errors import FieldExpressionError

router = APIRouter(tags=["Agents"])

LOGGER = logging.getLogger(__name__)


@router.get("/org/{organization_id}/agents", response_model=list[AgentWithGraphRunnersSchema], deprecated=True)
def get_all_agents(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> list[AgentWithGraphRunnersSchema]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_all_agents_service(session, organization_id)
    except Exception as e:
        LOGGER.error(f"Failed to fetch agents for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/agents/{project_id}/versions/{graph_runner_id}", response_model=AgentInfoSchema)
def get_agent_by_id(
    project_id: UUID,
    graph_runner_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> AgentInfoSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_agent_by_id_service(session, project_id, graph_runner_id)
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except GraphNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(f"Failed to fetch agent {project_id} version {graph_runner_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to fetch agent {project_id} version {graph_runner_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/org/{organization_id}/agents", response_model=ProjectWithGraphRunnersSchema)
def create_agent(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    agent_data: ProjectAgentSchema,
    session: Session = Depends(get_db),
) -> ProjectWithGraphRunnersSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return create_new_agent_service(session, user.id, organization_id, agent_data)
    except InvalidAgentTemplate as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to create agent for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put("/agents/{project_id}/versions/{graph_runner_id}", response_model=GraphUpdateResponse)
async def update_agent(
    project_id: UUID,
    graph_runner_id: UUID,
    agent_data: AgentUpdateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> GraphUpdateResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return await update_agent_service(session, user.id, project_id, graph_runner_id, agent_data)
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except GraphNotBoundToProjectError as e:
        LOGGER.error(
            f"Graph runner {graph_runner_id} is not bound to project {project_id} when updating graph",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
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
    except MCPConnectionError as e:
        LOGGER.error(
            f"MCP connection failed for project {project_id} runner {graph_runner_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MissingIntegrationError as e:
        LOGGER.error(
            f"Missing integration for project {project_id} version {graph_runner_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to update agent {project_id} version {graph_runner_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
