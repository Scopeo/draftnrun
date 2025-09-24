from uuid import UUID

from pydantic import BaseModel


class PortMappingSchema(BaseModel):
    source_instance_id: UUID
    source_port_name: str
    target_instance_id: UUID
    target_port_name: str
    # TODO: Use enum
    dispatch_strategy: str = "direct"
