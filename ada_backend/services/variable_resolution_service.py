import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories import variable_definitions_repository, variable_sets_repository

LOGGER = logging.getLogger(__name__)


def resolve_variables(
    session: Session,
    organization_id: UUID,
    set_ids: list[str],
) -> dict[str, Any]:
    """Resolve variables from definitions + multiple sets.

    Merge order: defaults → set_ids[0] → set_ids[1] → ...
    Returns dict[str, Any] of fully resolved values (ready for engine layer).
    """
    defs = variable_definitions_repository.list_org_definitions(session, organization_id)

    # 1. Start with defaults
    resolved: dict[str, Any] = {}
    for d in defs:
        resolved[d.name] = d.default_value

    # 2. Layer each set in order (later overrides earlier)
    for sid in set_ids:
        org_set = variable_sets_repository.get_org_variable_set(session, organization_id, sid)
        if org_set:
            for name, value in org_set.values.items():
                if name in resolved:
                    resolved[name] = value

    return resolved
