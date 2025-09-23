from typing import Optional
from uuid import UUID


class AgentSchema:
    name: str
    description: Optional[str]
    organization_id: UUID
    system_prompt: str
    model_config_id: UUID
    tools: list[UUID]


class AgentUpdateSchema(AgentSchema):
    id: UUID
