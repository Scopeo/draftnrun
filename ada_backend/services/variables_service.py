import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import SetType, VariableType
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
from ada_backend.services.errors import IntegrationSetProtectedError, VariableDefinitionNotFound, VariableSetNotFound

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


def set_to_response(variable_set: db.OrgVariableSet) -> VariableSetResponse:
    return VariableSetResponse(
        id=variable_set.id,
        organization_id=variable_set.organization_id,
        project_id=variable_set.project_id,
        set_id=variable_set.set_id,
        set_type=variable_set.set_type,
        values=variable_set.values,
        oauth_connection_id=variable_set.oauth_connection_id,
        created_at=str(variable_set.created_at),
        updated_at=str(variable_set.updated_at),
    )


def list_definitions_service(
    session: Session,
    organization_id: UUID,
    project_id: Optional[UUID] = None,
    var_type: Optional[VariableType] = None,
    exclude_type: Optional[VariableType] = None,
) -> list[VariableDefinitionResponse]:
    defs = list_org_definitions(session, organization_id, project_id=project_id, var_type=var_type, exclude_type=exclude_type)
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
    set_type: Optional[SetType] = None,
) -> VariableSetListResponse:
    sets = list_org_variable_sets(session, organization_id, set_type=set_type)
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
    existing = get_org_variable_set(session, organization_id, set_id)
    if existing and existing.set_type == SetType.INTEGRATION:
        raise IntegrationSetProtectedError(set_id)
    variable_set = upsert_org_variable_set(session, organization_id, set_id, values)
    return set_to_response(variable_set)


def delete_set_service(
    session: Session,
    organization_id: UUID,
    set_id: str,
) -> bool:
    existing = get_org_variable_set(session, organization_id, set_id)
    if existing and existing.set_type == SetType.INTEGRATION:
        raise IntegrationSetProtectedError(set_id)
    deleted = delete_org_variable_set(session, organization_id, set_id)
    if not deleted:
        raise VariableSetNotFound(set_id, organization_id)
    return deleted
