from typing import Annotated, List
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
    KnowledgeChunk,
    KnowledgeDocumentsListResponse,
    KnowledgeDocumentWithChunks,
)
from ada_backend.services.knowledge_service import (
    delete_chunk_service,
    delete_document_service,
    get_document_with_chunks_service,
    list_documents_service,
    update_document_chunks_service,
)


router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.get(
    "/organizations/{organization_id}/sources/{source_id}/documents", response_model=KnowledgeDocumentsListResponse
)
def list_documents(
    organization_id: UUID,
    source_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> KnowledgeDocumentsListResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    return list_documents_service(session, organization_id, source_id)


@router.get(
    "/organizations/{organization_id}/sources/{source_id}/documents/{document_id}",
    response_model=KnowledgeDocumentWithChunks,
)
def get_document(
    organization_id: UUID,
    source_id: UUID,
    document_id: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value))
    ],
    session: Session = Depends(get_db),
) -> KnowledgeDocumentWithChunks:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    return get_document_with_chunks_service(
        session,
        organization_id,
        source_id,
        document_id,
    )


@router.put(
    "/organizations/{organization_id}/sources/{source_id}/documents/{document_id}",
    response_model=List[KnowledgeChunk],
)
async def update_document(
    organization_id: UUID,
    source_id: UUID,
    document_id: str,
    chunks: List[KnowledgeChunk],
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> List[KnowledgeChunk]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    return await update_document_chunks_service(session, organization_id, source_id, chunks)


@router.delete("/organizations/{organization_id}/sources/{source_id}/documents/{document_id}")
def delete_document(
    organization_id: UUID,
    source_id: UUID,
    document_id: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    delete_document_service(session, organization_id, source_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/organizations/{organization_id}/sources/{source_id}/chunks/{chunk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chunk(
    organization_id: UUID,
    source_id: UUID,
    chunk_id: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value))
    ],
    session: Session = Depends(get_db),
) -> Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    await delete_chunk_service(session, organization_id, source_id, chunk_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
