from typing import Optional
from uuid import UUID

from engine.trace import models as db


def get_organization_token_usage(organization_id: UUID) -> Optional[db.OrganizationUsage]:
    """
    Retrieves token usage for an organization from the trace database.

    Args:
        organization_id (UUID): ID of the organization.

    Returns:
        Optional[db.OrganizationUsage]: The OrganizationUsage object if found, otherwise None.
    """
    from engine.trace.sql_exporter import get_session_trace

    session = get_session_trace()
    try:
        return session.query(db.OrganizationUsage).filter_by(organization_id=str(organization_id)).first()
    finally:
        session.close()
