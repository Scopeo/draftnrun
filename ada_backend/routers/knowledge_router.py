from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.knowledge_schema import (
    CreateKnowledgeChunkRequest,
    KnowledgeChunk,
    KnowledgeFileDetail,
    KnowledgeFileListResponse,
    UpdateKnowledgeChunkRequest,
)
from ada_backend.services.knowledge_service import (
    delete_file_for_data_source,
    delete_chunk_for_data_source,
    create_chunk_for_data_source,
    update_chunk_for_data_source,
    get_file_detail_for_data_source,
    list_files_for_data_source,
)


router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.get("/organizations/{organization_id}/sources/{source_id}/files", response_model=KnowledgeFileListResponse)
def list_files(
    organization_id: UUID,
    source_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> KnowledgeFileListResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return list_files_for_data_source(session, organization_id, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/organizations/{organization_id}/sources/{source_id}/files/{file_id}",
    response_model=KnowledgeFileDetail,
)
def get_file_detail(
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> KnowledgeFileDetail:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_file_detail_for_data_source(session, organization_id, source_id, file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/organizations/{organization_id}/sources/{source_id}/files/{file_id}")
def delete_file(
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        delete_file_for_data_source(session, organization_id, source_id, file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/organizations/{organization_id}/sources/{source_id}/files/{file_id}/chunks",
    response_model=KnowledgeChunk,
    status_code=status.HTTP_201_CREATED,
)
def create_chunk(
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
    request: CreateKnowledgeChunkRequest,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> KnowledgeChunk:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return create_chunk_for_data_source(session, organization_id, source_id, file_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/organizations/{organization_id}/sources/{source_id}/chunks/{chunk_id}",
    response_model=KnowledgeChunk,
)
def update_chunk(
    organization_id: UUID,
    source_id: UUID,
    chunk_id: str,
    request: UpdateKnowledgeChunkRequest,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> KnowledgeChunk:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return update_chunk_for_data_source(session, organization_id, source_id, chunk_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/organizations/{organization_id}/sources/{source_id}/chunks/{chunk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_chunk(
    organization_id: UUID,
    source_id: UUID,
    chunk_id: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        delete_chunk_for_data_source(session, organization_id, source_id, chunk_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
