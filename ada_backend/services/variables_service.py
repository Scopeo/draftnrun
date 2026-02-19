import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.variable_definitions_repository import (
    delete_org_definition,
    list_org_definitions,
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


def definition_to_response(definition: db.OrgVariableDefinition) -> VariableDefinitionResponse:
    return VariableDefinitionResponse(
        id=definition.id,
        organization_id=definition.organization_id,
        project_id=definition.project_id,
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


def set_to_response(variable_set: db.OrgVariableSet) -> VariableSetResponse:
    return VariableSetResponse(
        id=variable_set.id,
        organization_id=variable_set.organization_id,
        project_id=variable_set.project_id,
        set_id=variable_set.set_id,
        values=variable_set.values,
        created_at=str(variable_set.created_at),
        updated_at=str(variable_set.updated_at),
    )


def list_definitions_service(
    session: Session,
    organization_id: UUID,
) -> list[VariableDefinitionResponse]:
    defs = list_org_definitions(session, organization_id)
    return [definition_to_response(definition) for definition in defs]


def upsert_definition_service(
    session: Session,
    organization_id: UUID,
    name: str,
    body: VariableDefinitionUpsertRequest,
) -> VariableDefinitionResponse:
    fields = body.model_dump(exclude_none=True)
    definition = upsert_org_definition(session, organization_id, name, **fields)
    return definition_to_response(definition)


def delete_definition_service(
    session: Session,
    organization_id: UUID,
    name: str,
) -> bool:
    deleted = delete_org_definition(session, organization_id, name)
    if not deleted:
        raise VariableDefinitionNotFound(name, organization_id)
    return deleted


def list_sets_service(
    session: Session,
    organization_id: UUID,
) -> VariableSetListResponse:
    sets = list_org_variable_sets(session, organization_id)
    return VariableSetListResponse(variable_sets=[set_to_response(variable_set) for variable_set in sets])


def get_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> VariableSetResponse:
    variable_set = get_org_variable_set(session, organization_id, set_id)
    if not variable_set:
        raise VariableSetNotFound(set_id, organization_id)
    return set_to_response(variable_set)


def upsert_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
    values: dict,
) -> VariableSetResponse:
    variable_set = upsert_org_variable_set(session, organization_id, set_id, values)
    return set_to_response(variable_set)


def delete_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> bool:
    deleted = delete_org_variable_set(session, organization_id, set_id)
    if not deleted:
        raise VariableSetNotFound(set_id, organization_id)
    return deleted
