from uuid import UUID
from pydantic import BaseModel


class Template(BaseModel):
    template_graph_runner_id: UUID
    project_id: UUID
    name: str
    description: str
