from uuid import UUID
from pydantic import BaseModel
from typing import Optional


class InputTemplate(BaseModel):
    template_graph_runner_id: UUID
    template_project_id: UUID


class TemplateResponse(InputTemplate):
    name: Optional[str] = None
    description: Optional[str] = None
