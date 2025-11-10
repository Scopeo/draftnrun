from typing import Optional
from uuid import UUID

from ada_backend.database.models import OrganizationUsage
from engine.trace.sql_exporter import get_session_trace


def get_organization_token_usage(organization_id: UUID) -> Optional[OrganizationUsage]:
    """
    Retrieves token usage for an organization from the trace database.

    Args:
        organization_id (UUID): ID of the organization.

    Returns:
        Optional[OrganizationUsage]: The OrganizationUsage object if found, otherwise None.
    """
    session = get_session_trace()
    try:
        return session.query(OrganizationUsage).filter_by(organization_id=str(organization_id)).first()
    finally:
        session.close()
