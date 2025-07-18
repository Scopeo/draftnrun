from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.integration_repository import upsert_project_integration
from ada_backend.schemas.integration_schema import CreateProjectIntegrationSchema, IntegrationSecretResponse


async def add_or_update_integration_secrets_service(
    session: Session,
    project_id: UUID,
    integration_id: UUID,
    create_project_integration: CreateProjectIntegrationSchema,
) -> IntegrationSecretResponse:
    integration_secret = upsert_project_integration(
        session=session,
        project_id=project_id,
        integration_id=integration_id,
        access_token=create_project_integration.access_token,
        refresh_token=create_project_integration.refresh_token,
        expires_in=create_project_integration.expires_in,
        token_last_updated=create_project_integration.token_last_updated,
    )
    return IntegrationSecretResponse(
        integration_id=integration_id,
        secret_id=integration_secret.id,
    )
