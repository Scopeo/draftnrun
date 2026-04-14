import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import VariableType
from ada_backend.repositories.organization_repository import (
    list_variable_secrets_for_definitions,
    list_variable_secrets_for_set,
)
from ada_backend.repositories.variable_definitions_repository import list_org_definitions
from ada_backend.repositories.variable_sets_repository import get_org_variable_set
from engine.secret import SecretValue

LOGGER = logging.getLogger(__name__)


def resolve_variables(
    session: Session,
    organization_id: UUID,
    set_ids: list[str],
    project_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Resolve variables from definitions + multiple sets.

    Merge order: defaults → set_ids[0] → set_ids[1] → ...
    Returns dict[str, Any] of fully resolved values (ready for engine layer).

    TODO: after variable values are normalized, resolve from a single value source
    per definition/profile and keep type-specific handling in one place.
    """
    variable_definitions = list_org_definitions(session, organization_id, project_id=project_id)
    definition_ids = [d.id for d in variable_definitions]
    definitions_by_name = {definition.name: definition for definition in variable_definitions}

    # 1. Start with defaults
    resolved: dict[str, Any] = {}
    default_secrets = list_variable_secrets_for_definitions(session, definition_ids, variable_set_id=None)
    secret_defaults = {s.variable_definition_id: s for s in default_secrets}

    for definition in variable_definitions:
        if definition.type == VariableType.SECRET:
            row = secret_defaults.get(definition.id)
            if row:
                resolved[definition.name] = SecretValue(row.get_secret())
        elif definition.default_value is not None:
            resolved[definition.name] = definition.default_value

    # 2. Layer each set in order (later overrides earlier)
    for set_id in set_ids:
        org_set = get_org_variable_set(session, organization_id, set_id)
        if not org_set:
            continue

        if org_set.variable_type == VariableType.OAUTH:
            for name, value in org_set.values.items():
                resolved[name] = value
            continue

        set_secrets = list_variable_secrets_for_set(session, org_set.id)
        secrets_by_def = {s.variable_definition_id: s for s in set_secrets}
        for name, value in org_set.values.items():
            definition = definitions_by_name.get(name)
            if definition and definition.type != VariableType.SECRET:
                resolved[name] = value

        for definition in variable_definitions:
            if definition.type == VariableType.SECRET:
                row = secrets_by_def.get(definition.id)
                if row:
                    resolved[definition.name] = SecretValue(row.get_secret())
    return resolved
