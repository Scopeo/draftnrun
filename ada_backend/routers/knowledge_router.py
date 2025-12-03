from typing import Annotated
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.knowledge_schema import (
    KnowledgeDocumentWithChunks,
    KnowledgeDocumentsListResponse,
)
from ada_backend.services.knowledge_service import (
    delete_document_service,
    delete_chunk_service,
    get_document_with_chunks_service,
    list_documents_service,
)
from ada_backend.services.knowledge.errors import (
    KnowledgeServiceQdrantConfigurationError,
    KnowledgeServiceQdrantOperationError,
    KnowledgeSourceNotFoundError,
    KnowledgeServiceDocumentNotFoundError,
    KnowledgeServiceDBSourceConfigError,
    KnowledgeServicePageOutOfRangeError,
)

LOGGER = logging.getLogger(__name__)


router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.get(
    "/organizations/{organization_id}/sources/{source_id}/documents", response_model=KnowledgeDocumentsListResponse
)
def list_documents(
    organization_id: UUID,
    source_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> KnowledgeDocumentsListResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return list_documents_service(session, organization_id, source_id)
    except KnowledgeSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KnowledgeServiceDBSourceConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KnowledgeServiceQdrantConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to list files for source {source_id} in organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/organizations/{organization_id}/sources/{source_id}/documents/{document_id}",
    response_model=KnowledgeDocumentWithChunks,
)
def get_document(
    organization_id: UUID,
    source_id: UUID,
    document_id: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    session: Session = Depends(get_db),
) -> KnowledgeDocumentWithChunks:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_document_with_chunks_service(
            session, organization_id, source_id, document_id, page=page, page_size=page_size
        )
    except KnowledgeSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KnowledgeServiceDocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KnowledgeServiceDBSourceConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KnowledgeServiceQdrantConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KnowledgeServicePageOutOfRangeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            (
                f"Failed to get document detail {document_id} for source {source_id} "
                f"in organization {organization_id}: {str(e)}"
            ),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/organizations/{organization_id}/sources/{source_id}/documents/{document_id}")
def delete_document(
    organization_id: UUID,
    source_id: UUID,
    document_id: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        delete_document_service(session, organization_id, source_id, document_id)
    except KnowledgeSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KnowledgeServiceDocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KnowledgeServiceDBSourceConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KnowledgeServiceQdrantConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            (
                f"Failed to delete document {document_id} for source {source_id} "
                f"in organization {organization_id}: {str(e)}"
            ),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e
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
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        await delete_chunk_service(session, organization_id, source_id, chunk_id)
    except KnowledgeSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KnowledgeServiceDBSourceConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KnowledgeServiceQdrantConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KnowledgeServiceQdrantOperationError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to delete chunk {chunk_id} for source {source_id} in organization {organization_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
