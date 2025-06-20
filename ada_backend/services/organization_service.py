from uuid import UUID
import logging

from sqlalchemy.orm import Session

from ada_backend.repositories.graph_runner_repository import get_graph_runners_by_project
from ada_backend.repositories.organization_repository import (
    delete_organization_secret,
    get_organization_secrets,
    upsert_organization_secret,
)
from ada_backend.repositories.project_repository import get_projects_by_organization_service
from ada_backend.schemas.organization_schema import OrganizationSecretResponse, OrganizationGetSecretKeysResponse
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_service


LOGGER = logging.getLogger(__name__)


async def update_api_key_in_organization(session: Session, organization_id: UUID):
    org_projects = get_projects_by_organization_service(session, organization_id)
    for project in org_projects:
        graph_runners = get_graph_runners_by_project(session, project.id)
        for graph_runner in graph_runners:
            try:
                graph_project = get_graph_service(session, project_id=project.id, graph_runner_id=graph_runner.id)
                await update_graph_service(session, graph_runner.id, project.id, graph_project)
            except Exception as e:
                LOGGER.error(
                    f"Failed to update graph for project {project.id} and graph runner {graph_runner.id}: {str(e)}"
                )
                continue


def get_secret_keys_service(
    sqlaclhemy_db_session: Session,
    organization_id: UUID,
) -> OrganizationGetSecretKeysResponse:
    organization_secrets = get_organization_secrets(
        session=sqlaclhemy_db_session,
        organization_id=organization_id,
    )
    return OrganizationGetSecretKeysResponse(
        organization_id=organization_id,
        secret_keys=[organization_secret.key for organization_secret in organization_secrets],
    )


async def upsert_secret_to_org_service(
    sqlaclhemy_db_session: Session, organization_id: UUID, secret_key: str, secret: str
):
    organization_secret = upsert_organization_secret(
        session=sqlaclhemy_db_session,
        organization_id=organization_id,
        key=secret_key,
        secret=secret,
    )
    try:
        await update_api_key_in_organization(session=sqlaclhemy_db_session, organization_id=organization_id)
    except Exception as e:
        raise ValueError(
            f"Failed to update API key in organization {organization_id} for key {secret_key}: {str(e)}"
        ) from e
    return OrganizationSecretResponse(
        organization=organization_secret.organization_id,
        secret_key=organization_secret.key,
    )


def delete_secret_to_org_service(
    sqlaclhemy_db_session: Session, organization_id: UUID, secret_key: str
) -> OrganizationSecretResponse:
    deleted_organization_secret = delete_organization_secret(
        session=sqlaclhemy_db_session,
        organization_id=organization_id,
        key=secret_key,
    )
    return OrganizationSecretResponse(
        organization=deleted_organization_secret.organization_id,
        secret_key=deleted_organization_secret.key,
    )
