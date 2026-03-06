import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import VariableType
from ada_backend.repositories.organization_repository import (
    get_variable_secret,
    list_variable_secrets_for_set,
    upsert_variable_secret,
)
from ada_backend.repositories.project_repository import get_project
from ada_backend.repositories.variable_definitions_repository import (
    delete_org_definition,
    list_org_definitions,
    replace_definition_projects,
    upsert_org_definition,
)
from ada_backend.repositories.variable_sets_repository import (
    delete_org_variable_set,
    get_org_variable_set,
    list_org_variable_sets,
    upsert_org_variable_set,
)
from ada_backend.schemas.variable_schemas import (
    VariableDefinitionResponse,
    VariableDefinitionUpsertRequest,
    VariableSetListResponse,
    VariableSetResponse,
)
from ada_backend.services.errors import OAuthSetProtectedError, VariableDefinitionNotFound, VariableSetNotFound

LOGGER = logging.getLogger(__name__)


def _validate_project_ids_belong_to_org(session: Session, organization_id: UUID, project_ids: list[UUID]) -> None:
    for project_id in project_ids:
        project = get_project(session, project_id=project_id)
        if not project or project.organization_id != organization_id:
            raise ValueError(f"Project {project_id} does not belong to organization {organization_id}")


def definition_to_response(
    session: Session,
    definition: db.OrgVariableDefinition,
) -> VariableDefinitionResponse:
    is_secret = definition.type == VariableType.SECRET
    return VariableDefinitionResponse(
        id=definition.id,
        organization_id=definition.organization_id,
        project_ids=[assoc.project_id for assoc in definition.project_associations],
        name=definition.name,
        type=definition.type,
        description=definition.description,
        required=definition.required,
        default_value=None if is_secret else definition.default_value,
        has_default_value=get_variable_secret(session, definition.id) is not None if is_secret else False,
        metadata=definition.variable_metadata,
        editable=definition.editable,
        display_order=definition.display_order,
        created_at=str(definition.created_at),
        updated_at=str(definition.updated_at),
    )


def _build_definition_map(definitions: list[db.OrgVariableDefinition]) -> dict[str, db.OrgVariableDefinition]:
    return {definition.name: definition for definition in definitions}


def _mask_set_values(
    session: Session,
    variable_set: db.OrgVariableSet,
) -> dict[str, Any]:
    response_values: dict[str, Any] = dict(variable_set.values or {})

    set_secrets = list_variable_secrets_for_set(session, variable_set.id)
    for secret in set_secrets:
        response_values[secret.key] = {"has_value": True}

    return response_values


def set_to_response(
    session: Session,
    variable_set: db.OrgVariableSet,
) -> VariableSetResponse:
    return VariableSetResponse(
        id=variable_set.id,
        organization_id=variable_set.organization_id,
        project_id=variable_set.project_id,
        set_id=variable_set.set_id,
        variable_type=variable_set.variable_type,
        values=_mask_set_values(session, variable_set),
        oauth_connection_id=variable_set.oauth_connection_id,
        created_at=str(variable_set.created_at),
        updated_at=str(variable_set.updated_at),
    )


def list_definitions_service(
    session: Session,
    organization_id: UUID,
    project_id: Optional[UUID] = None,
    var_type: Optional[VariableType] = None,
) -> list[VariableDefinitionResponse]:
    defs = list_org_definitions(session, organization_id, project_id=project_id, var_type=var_type)
    return [definition_to_response(session, definition) for definition in defs]


def upsert_definition_service(
    session: Session,
    organization_id: UUID,
    name: str,
    body: VariableDefinitionUpsertRequest,
) -> VariableDefinitionResponse:
    fields = body.model_dump(exclude_none=True)
    project_ids = fields.pop("project_ids", None)
    # Remap "metadata" → "variable_metadata" (the Python attr; DB column is "metadata")
    if "metadata" in fields:
        fields["variable_metadata"] = fields.pop("metadata")
    plaintext_default_value = None
    if fields.get("type") == VariableType.SECRET:
        plaintext_default_value = fields.pop("default_value", None)
    definition = upsert_org_definition(session, organization_id, name, **fields)
    if plaintext_default_value is not None:
        upsert_variable_secret(session, organization_id, definition.id, None, definition.name, plaintext_default_value)
    if project_ids is not None:
        project_ids = list(set(project_ids))
        _validate_project_ids_belong_to_org(session, organization_id, project_ids)
        replace_definition_projects(session, definition.id, project_ids)
        session.refresh(definition)
    session.commit()
    return definition_to_response(session, definition)


def delete_definition_service(
    session: Session,
    organization_id: UUID,
    name: str,
) -> bool:
    deleted = delete_org_definition(session, organization_id, name)
    if not deleted:
        raise VariableDefinitionNotFound(name, organization_id)
    session.commit()
    return deleted


def list_sets_service(
    session: Session,
    organization_id: UUID,
    variable_type: Optional[VariableType] = None,
) -> VariableSetListResponse:
    sets = list_org_variable_sets(session, organization_id, variable_type=variable_type)
    return VariableSetListResponse(variable_sets=[set_to_response(session, variable_set) for variable_set in sets])


def get_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> VariableSetResponse:
    variable_set = get_org_variable_set(session, organization_id, set_id)
    if not variable_set:
        raise VariableSetNotFound(set_id, organization_id)
    return set_to_response(session, variable_set)


def upsert_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
    values: dict,
) -> VariableSetResponse:
    existing_set = get_org_variable_set(session, organization_id, set_id)
    if existing_set and existing_set.variable_type == VariableType.OAUTH:
        raise OAuthSetProtectedError(set_id)

    definitions_by_name = _build_definition_map(list_org_definitions(session, organization_id))

    plain_values: dict[str, Any] = {}
    secret_entries: list[tuple[db.OrgVariableDefinition, str]] = []

    for key, value in values.items():
        definition = definitions_by_name.get(key)
        if definition and definition.type == VariableType.SECRET:
            if value is not None:
                secret_entries.append((definition, str(value)))
            continue
        plain_values[key] = value

    variable_set = upsert_org_variable_set(session, organization_id, set_id, plain_values)

    for definition, secret_value in secret_entries:
        upsert_variable_secret(session, organization_id, definition.id, variable_set.id, definition.name, secret_value)

    return set_to_response(session, variable_set)


def delete_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> bool:
    existing = get_org_variable_set(session, organization_id, set_id)
    if existing and existing.variable_type == VariableType.OAUTH:
        raise OAuthSetProtectedError(set_id)
    deleted = delete_org_variable_set(session, organization_id, set_id)
    if not deleted:
        raise VariableSetNotFound(set_id, organization_id)
    return deleted
