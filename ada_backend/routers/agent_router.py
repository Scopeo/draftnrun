from uuid import UUID
from typing import Annotated, List
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    user_has_access_to_agent_dependency,
    user_has_access_to_organization_dependency,
    UserRights,
)
from ada_backend.schemas.agent_schema import AgentUpdateSchema, ProjectAgentSchema, AgentInfoSchema
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateResponse
from ada_backend.schemas.project_schema import ProjectWithGraphRunnersSchema
from ada_backend.services.agents_service import (
    create_new_agent_service,
    get_agent_by_id_service,
    get_all_agents_service,
    update_agent_service,
)
from ada_backend.services.errors import ProjectNotFound

router = APIRouter(tags=["Agents"])

LOGGER = logging.getLogger(__name__)


@router.get("/org/{organization_id}/agents", response_model=List[ProjectAgentSchema])
def get_all_agents(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> List[ProjectAgentSchema]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_all_agents_service(session, organization_id)
    except Exception as e:
        LOGGER.error(f"Error fetching agents for organization {organization_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error service: {str(e)}")


@router.get("/agents/{agent_id}/version/{version_id}", response_model=AgentInfoSchema)
def get_agent_by_id(
    agent_id: UUID,
    version_id: UUID,
    user: Annotated[SupabaseUser, Depends(user_has_access_to_agent_dependency(allowed_roles=UserRights.READER.value))],
    session: Session = Depends(get_db),
) -> AgentInfoSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_agent_by_id_service(session, agent_id, version_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="Agent not found")
    except Exception as e:
        LOGGER.error(f"Error fetching agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error service: {str(e)}")


@router.post("/org/{organization_id}/agents", response_model=ProjectWithGraphRunnersSchema)
def create_agent(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    agent_data: ProjectAgentSchema,
    session: Session = Depends(get_db),
) -> ProjectWithGraphRunnersSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return create_new_agent_service(session, user.id, organization_id, agent_data)
    except Exception as e:
        LOGGER.error(f"Error creating agent for organization {organization_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error service: {str(e)}")


@router.put("/agents/{agent_id}/version/{version_id}", response_model=GraphUpdateResponse)
async def update_agent(
    agent_id: UUID,
    version_id: UUID,
    agent_data: AgentUpdateSchema,
    user: Annotated[SupabaseUser, Depends(user_has_access_to_agent_dependency(allowed_roles=UserRights.WRITER.value))],
    session: Session = Depends(get_db),
) -> GraphUpdateResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return await update_agent_service(session, user.id, agent_id, version_id, agent_data)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="Agent not found")
    except Exception as e:
        LOGGER.error(f"Error updating agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error service: {str(e)}")
