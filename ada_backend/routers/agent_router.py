from uuid import UUID
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
)
from ada_backend.schemas.agent_schema import AgentSchema, AgentUpdateSchema
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.services.agents_service import (
    create_new_agent_service,
    delete_agent_service,
    get_agent_by_id_service,
    get_all_agents_service,
    update_agent_service,
)

router = APIRouter(tags=["Agents"])


@router.get("/org/{organization_id}/agents", response_model=List[AgentSchema])
def get_all_agents(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> List[AgentSchema]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    return get_all_agents_service(session, organization_id)


@router.get("/agents/{agent_id}", response_model=AgentSchema)
def get_agent_by_id(
    agent_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> AgentSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    agent = get_agent_by_id_service(session, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/org/{organization_id}/agents", response_model=AgentSchema)
def create_agent(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    agent_data: AgentSchema,
    session: Session = Depends(get_db),
) -> AgentSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    return create_new_agent_service(session, organization_id, agent_data)


def update_agent(
    agent_id: UUID,
    agent_data: AgentUpdateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> AgentUpdateSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    agent = update_agent_service(session, agent_id, agent_data)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/agents/{agent_id}", status_code=204)
def delete_agent(
    agent_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    return delete_agent_service(session, agent_id)
