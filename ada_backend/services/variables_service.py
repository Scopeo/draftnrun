import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import CIPHER, VariableType
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
from ada_backend.services.errors import VariableDefinitionNotFound, VariableSetNotFound

LOGGER = logging.getLogger(__name__)


def _validate_project_ids_belong_to_org(session: Session, organization_id: UUID, project_ids: list[UUID]) -> None:
    for project_id in project_ids:
        project = get_project(session, project_id=project_id)
        if not project or project.organization_id != organization_id:
            raise ValueError(f"Project {project_id} does not belong to organization {organization_id}")


def definition_to_response(definition: db.OrgVariableDefinition) -> VariableDefinitionResponse:
    return VariableDefinitionResponse(
        id=definition.id,
        organization_id=definition.organization_id,
        project_ids=[assoc.project_id for assoc in definition.project_associations],
        name=definition.name,
        type=definition.type,
        description=definition.description,
        required=definition.required,
        default_value=definition.default_value,
        metadata=definition.variable_metadata,
        editable=definition.editable,
        display_order=definition.display_order,
        created_at=str(definition.created_at),
        updated_at=str(definition.updated_at),
    )


def _build_definition_map(definitions: list[db.OrgVariableDefinition]) -> dict[str, db.OrgVariableDefinition]:
    return {definition.name: definition for definition in definitions}


def _mask_set_values(
    variable_set: db.OrgVariableSet,
    definitions_by_name: dict[str, db.OrgVariableDefinition],
) -> dict[str, Any]:
    response_values: dict[str, Any] = dict(variable_set.values or {})

    for key, encrypted_value in (variable_set.encrypted_values or {}).items():
        definition = definitions_by_name.get(key)
        if definition and definition.type == VariableType.SECRET:
            response_values[key] = {"is_set": bool(encrypted_value)}

    for key, value in list(response_values.items()):
        definition = definitions_by_name.get(key)
        if definition and definition.type == VariableType.SECRET:
            response_values[key] = {"is_set": bool((variable_set.encrypted_values or {}).get(key))}

    return response_values


def set_to_response(
    variable_set: db.OrgVariableSet,
    definitions_by_name: dict[str, db.OrgVariableDefinition],
) -> VariableSetResponse:
    return VariableSetResponse(
        id=variable_set.id,
        organization_id=variable_set.organization_id,
        project_id=variable_set.project_id,
        set_id=variable_set.set_id,
        values=_mask_set_values(variable_set, definitions_by_name),
        created_at=str(variable_set.created_at),
        updated_at=str(variable_set.updated_at),
    )


def list_definitions_service(
    session: Session,
    organization_id: UUID,
    project_id: Optional[UUID] = None,
) -> list[VariableDefinitionResponse]:
    defs = list_org_definitions(session, organization_id, project_id=project_id)
    return [definition_to_response(definition) for definition in defs]


def upsert_definition_service(
    session: Session,
    organization_id: UUID,
    name: str,
    body: VariableDefinitionUpsertRequest,
) -> VariableDefinitionResponse:
    fields = body.model_dump(exclude_none=True)
    project_ids = fields.pop("project_ids", None)
    definition = upsert_org_definition(session, organization_id, name, **fields)
    if project_ids is not None:
        project_ids = list(set(project_ids))
        _validate_project_ids_belong_to_org(session, organization_id, project_ids)
        replace_definition_projects(session, definition.id, project_ids)
        session.refresh(definition)
    session.commit()
    return definition_to_response(definition)


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
) -> VariableSetListResponse:
    sets = list_org_variable_sets(session, organization_id)
    definitions_by_name = _build_definition_map(list_org_definitions(session, organization_id))
    return VariableSetListResponse(
        variable_sets=[set_to_response(variable_set, definitions_by_name) for variable_set in sets]
    )


def get_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> VariableSetResponse:
    variable_set = get_org_variable_set(session, organization_id, set_id)
    if not variable_set:
        raise VariableSetNotFound(set_id, organization_id)
    definitions_by_name = _build_definition_map(list_org_definitions(session, organization_id))
    return set_to_response(variable_set, definitions_by_name)


def upsert_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
    values: dict,
) -> VariableSetResponse:
    definitions_by_name = _build_definition_map(list_org_definitions(session, organization_id))
    existing_set = get_org_variable_set(session, organization_id, set_id)

    plain_values: dict[str, Any] = {}
    encrypted_values = dict(existing_set.encrypted_values or {}) if existing_set else {}

    for key, value in values.items():
        definition = definitions_by_name.get(key)
        if definition and definition.type == VariableType.SECRET:
            if value is None:
                continue
            encrypted_values[key] = CIPHER.encrypt(str(value).encode()).decode()
            continue
        plain_values[key] = value

    variable_set = upsert_org_variable_set(session, organization_id, set_id, plain_values, encrypted_values)
    return set_to_response(variable_set, definitions_by_name)


def delete_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> bool:
    deleted = delete_org_variable_set(session, organization_id, set_id)
    if not deleted:
        raise VariableSetNotFound(set_id, organization_id)
    return deleted
