from dataclasses import dataclass
from typing import Any, List

from ada_backend.services.errors import ServiceError


class KnowledgeServiceError(ServiceError):
    """Base exception for Knowledge service errors."""

    code = "knowledge_service_error"


class KnowledgeServiceQdrantConfigurationError(KnowledgeServiceError):
    """Raised when Qdrant configuration is missing or invalid."""

    code = "qdrant_configuration_error"
    status_code = 500


class KnowledgeServiceQdrantOperationError(KnowledgeServiceError):
    """Raised when Qdrant operations fail at runtime."""

    code = "qdrant_operation_error"
    status_code = 500


@dataclass
class KnowledgeServiceQdrantChunkDeletionError(KnowledgeServiceQdrantOperationError):
    chunk_id: str
    collection_name: str
    reason: str

    code = "qdrant_chunk_deletion_error"

    def __post_init__(self):
        super().__init__(f"Failed to delete chunk {self.chunk_id} from vector store: {self.reason}")


@dataclass
class KnowledgeServiceQdrantMissingFieldsError(KnowledgeServiceQdrantConfigurationError):
    source_id: str
    missing: List[str]

    code = "qdrant_missing_fields"

    def __post_init__(self):
        super().__init__(f"Data source '{self.source_id}' is missing required fields: {', '.join(self.missing)}")


@dataclass
class KnowledgeServiceInvalidQdrantSchemaError(KnowledgeServiceQdrantConfigurationError):
    source_id: str
    schema: Any
    reason: str

    code = "invalid_qdrant_schema"

    def __post_init__(self):
        super().__init__(f"Data source '{self.source_id}' has invalid vector search configuration: {self.reason}")


@dataclass
class KnowledgeServiceInvalidEmbeddingModelReferenceError(KnowledgeServiceQdrantConfigurationError):
    source_id: str
    embedding_model_reference: str
    reason: str

    code = "invalid_embedding_model_reference"

    def __post_init__(self):
        super().__init__(
            f"Data source '{self.source_id}' has invalid embedding_model_reference "
            f"{self.embedding_model_reference!r}: {self.reason}"
        )


@dataclass
class KnowledgeServiceQdrantCollectionNotFoundError(KnowledgeServiceQdrantConfigurationError):
    source_id: str
    collection_name: str

    code = "qdrant_collection_not_found"
    status_code = 404

    def __post_init__(self):
        super().__init__(
            f"Data source '{self.source_id}' references vector collection "
            f"'{self.collection_name}' which does not exist"
        )


@dataclass
class KnowledgeServiceQdrantServiceCreationError(KnowledgeServiceQdrantOperationError):
    source_id: str
    reason: str

    code = "qdrant_service_creation_failed"

    def __post_init__(self):
        super().__init__(f"Failed to initialize vector search for source '{self.source_id}': {self.reason}")


@dataclass
class KnowledgeServiceQdrantCollectionCheckError(KnowledgeServiceQdrantOperationError):
    source_id: str
    collection_name: str
    reason: str

    code = "qdrant_collection_check_failed"

    def __post_init__(self):
        super().__init__(
            f"Failed to check Qdrant collection '{self.collection_name}' existence "
            f"for source '{self.source_id}': {self.reason}"
        )


class KnowledgeSourceNotFoundError(KnowledgeServiceError):
    """Raised when a data source is not found."""

    status_code = 404

    def __init__(self, source_id: str, organization_id: str):
        self.source_id = source_id
        self.organization_id = organization_id
        super().__init__(f"Data source '{source_id}' not found for organization '{organization_id}'")


class KnowledgeServiceDocumentNotFoundError(KnowledgeServiceError):
    """Raised when a document cannot be found for a given source."""

    status_code = 404

    def __init__(self, document_id: str, source_id: str):
        self.document_id = document_id
        self.source_id = source_id
        super().__init__(f"Document with id='{document_id}' not found for source '{source_id}'")


class KnowledgeMaxChunkSizeError(KnowledgeServiceError):
    """Raised when a chunk size is too large."""

    status_code = 400

    def __init__(self, token_count: int, max_chunk_tokens: int):
        self.token_count = token_count
        self.max_chunk_tokens = max_chunk_tokens
        super().__init__(
            f"Chunk content exceeds maximum allowed token count: {self.max_chunk_tokens}. "
            f"Token count: {self.token_count}"
        )


class KnowledgeEmptyChunkError(KnowledgeServiceError):
    """Raised when a chunk content is empty."""

    status_code = 400

    def __init__(self):
        super().__init__("Chunk content cannot be empty.")


class KnowledgeServiceDBError(KnowledgeServiceError):
    """Base exception for database-related errors in the knowledge service."""

    status_code = 500


class KnowledgeServiceDBSourceConfigError(KnowledgeServiceDBError):
    """Raised when data source is missing required database configuration (e.g., schema/table identifiers)."""


@dataclass
class KnowledgeServiceDBChunkDeletionError(KnowledgeServiceDBError):
    chunk_id: str
    table_name: str
    schema_name: str
    reason: str

    code = "db_chunk_deletion_error"

    def __post_init__(self):
        super().__init__(
            f"Failed to delete chunk {self.chunk_id} from source database: {self.reason}"
        )
