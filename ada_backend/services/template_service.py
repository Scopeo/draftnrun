from sqlalchemy.orm import Session

from ada_backend.repositories.template_repository import retrieve_production_templates
from ada_backend.schemas.template_schema import TemplateResponse


def list_templates_services(
    session: Session,
) -> list[TemplateResponse]:
    templates = []
    production_templates = retrieve_production_templates(session)
    for project, project_env_gr in production_templates:
        templates.append(
            TemplateResponse(
                template_graph_runner_id=project_env_gr.graph_runner_id,
                template_project_id=project.id,
                name=project.name,
                description=project.description,
            )
        )
    return templates
