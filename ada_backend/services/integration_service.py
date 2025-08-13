from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.integration_repository import insert_secret_integration, get_integration
from ada_backend.schemas.integration_schema import CreateProjectIntegrationSchema, IntegrationSecretResponse


async def add_integration_secrets_service(
    session: Session,
    integration_id: UUID,
    create_project_integration: CreateProjectIntegrationSchema,
) -> IntegrationSecretResponse:
    # Look up the integration to determine if tokens expire
    integration = get_integration(session, integration_id)
    if not integration:
        raise ValueError(f"Integration with ID {integration_id} not found")
    
    # Slack tokens are non-expiring, all others (Gmail, etc.) are expiring
    is_expiring = integration.service != "slack sender"
    
    integration_secret = insert_secret_integration(
        session=session,
        integration_id=integration_id,
        access_token=create_project_integration.access_token,
        refresh_token=create_project_integration.refresh_token,
        expires_in=create_project_integration.expires_in,
        token_last_updated=create_project_integration.token_last_updated,
        is_expiring=is_expiring,
    )
    return IntegrationSecretResponse(
        integration_id=integration_id,
        secret_id=integration_secret.id,
    )
