"""
Simple offline database helper for organization access checks.
Directly connects to PostgreSQL when OFFLINE_MODE is enabled.
"""

from typing import Optional
from uuid import UUID
import logging
from urllib.parse import urlparse

import psycopg2
from ada_backend.schemas.auth_schema import OrganizationAccess
from settings import settings

logger = logging.getLogger(__name__)


def get_offline_org_access(user_id: str, organization_id: UUID) -> OrganizationAccess:
    """
    Check organization access by directly querying PostgreSQL.
    Used only when OFFLINE_MODE is True.

    Args:
        user_id: User UUID as string
        organization_id: Organization UUID

    Returns:
        OrganizationAccess with org_id and role
    """
    try:
        # Parse Supabase URL to get connection details
        # SUPABASE_PROJECT_URL format: http://localhost:54321 or https://project.supabase.co
        url = urlparse(settings.SUPABASE_PROJECT_URL)

        # For local Supabase: connect to localhost:54322 (postgres port)
        # For hosted: would need different connection string
        if url.hostname == "localhost":
            host = "localhost"
            port = 54322  # Standard Supabase local postgres port
        else:
            # For hosted Supabase, extract from URL
            host = url.hostname
            port = 5432

        # Connect directly to PostgreSQL using credentials from settings
        conn = psycopg2.connect(
            host=host,
            port=port,
            database="postgres",
            user=settings.SUPABASE_USERNAME or "postgres",
            password=settings.SUPABASE_PASSWORD or "postgres"
        )

        cursor = conn.cursor()

        # Query organization_members table directly
        cursor.execute(
            "SELECT role FROM organization_members WHERE user_id = %s AND org_id = %s LIMIT 1",
            (user_id, str(organization_id))
        )

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        # Check if user has membership
        if result:
            role = result[0]
            logger.info(f"Offline mode: User {user_id} has role '{role}' in org {organization_id}")
            return OrganizationAccess(org_id=organization_id, role=role)

        # No membership found - use default role
        logger.info(f"Offline mode: No membership found for user {user_id} in org {organization_id}, using default role '{settings.OFFLINE_DEFAULT_ROLE}'")
        return OrganizationAccess(org_id=organization_id, role=settings.OFFLINE_DEFAULT_ROLE)

    except Exception as e:
        # Database error - fail safe with default role
        logger.warning(f"Offline mode database error for user {user_id} in org {organization_id}: {e}")
        logger.info(f"Falling back to default role '{settings.OFFLINE_DEFAULT_ROLE}'")
        return OrganizationAccess(org_id=organization_id, role=settings.OFFLINE_DEFAULT_ROLE)