from uuid import UUID
import logging

from sqlalchemy.orm import Session
from ada_backend.repositories.template_repository import retrieve_production_templates
from ada_backend.schemas.template_schema import Template

TEMPLATE_ORGANIZATION_ID = "91669f17-430a-447e-a3e9-e7f065c2b54f"


def list_templates_services(
    session: Session,
) -> list[Template]:
    templates = []
    production_templates = retrieve_production_templates(session, TEMPLATE_ORGANIZATION_ID)
    for project, project_env_gr in production_templates:
        templates.append(
            Template(
                template_graph_runner_id=project_env_gr.graph_runner_id,
                project_id=project.id,
                name=project.name,
                description=project.description,
            )
        )
    return templates
