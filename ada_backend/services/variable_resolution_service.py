import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.variable_definitions_repository import list_org_definitions
from ada_backend.repositories.variable_sets_repository import get_org_variable_set

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
    variable_definitions = list_org_definitions(session, organization_id)
    defined_names = {definition.name for definition in variable_definitions}

    # 1. Start with defaults
    resolved: dict[str, Any] = {}
    for definition in variable_definitions:
        if definition.default_value is not None:
            resolved[definition.name] = definition.default_value

    # 2. Layer each set in order (later overrides earlier)
    for set_id in set_ids:
        org_set = get_org_variable_set(session, organization_id, set_id)
        if org_set:
            for name, value in org_set.values.items():
                if name in defined_names:
                    resolved[name] = value

    return resolved
