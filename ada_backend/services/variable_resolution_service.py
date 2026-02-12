import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import VariableType
from ada_backend.repositories import variable_definitions_repository, variable_sets_repository
from ada_backend.services.integration_service import get_oauth_access_token

LOGGER = logging.getLogger(__name__)


async def resolve_variables(
    session: Session,
    project_id: UUID,
    organization_id: UUID,
    set_ids: list[str],
) -> dict[str, Any]:
    """Resolve variables from definitions + multiple sets, with type-aware resolution.

    Merge order: defaults → set_ids[0] → set_ids[1] → ...
    Returns dict[str, Any] of fully resolved values (ready for engine layer).
    """
    defs = variable_definitions_repository.list_definitions(session, project_id)

    # 1. Start with defaults
    resolved: dict[str, Any] = {}
    defs_by_name = {}
    for d in defs:
        resolved[d.name] = d.default_value
        defs_by_name[d.name] = d

    # 2. Layer each set in order (later overrides earlier)
    for sid in set_ids:
        org_set = variable_sets_repository.get_org_variable_set(session, organization_id, sid)
        if org_set:
            for name, value in org_set.values.items():
                if name in resolved:
                    resolved[name] = value

    # 3. Type-specific resolution
    for name, value in list(resolved.items()):
        defn = defs_by_name.get(name)
        if not defn or not value:
            continue
        if defn.type == VariableType.OAUTH:
            provider = (defn.variable_metadata or {}).get("provider_config_key")
            if provider:
                try:
                    resolved[name] = await get_oauth_access_token(session, UUID(value), provider)
                except Exception as e:
                    LOGGER.error(f"Failed to resolve OAuth token for variable {name}: {e}", exc_info=True)

    return resolved
