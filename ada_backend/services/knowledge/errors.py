class KnowledgeServiceError(Exception):
    """Base exception for Knowledge service errors."""


class KnowledgeServiceChunkWrongSizeError(KnowledgeServiceError):
    """Raised when user attempts to create/update chunks with wrong token size."""


class KnowledgeServiceQdrantConfigurationError(KnowledgeServiceError):
    """Raised when Qdrant configuration is missing or invalid (validation/configuration errors)."""


class KnowledgeServiceQdrantOperationError(KnowledgeServiceError):
    """Raised when Qdrant operations fail at runtime (e.g., add/delete chunk failures)."""


class KnowledgeServiceSourceError(KnowledgeServiceError):
    """Raised when there is an error related to the source."""


class KnowledgeServiceFileNotFoundError(KnowledgeServiceError):
    """Raised when a file cannot be found for a given source."""


class KnowledgeServiceDBError(KnowledgeServiceError):
    """Base exception for database-related errors in the knowledge service."""


class KnowledgeServiceDBSourceConfigError(KnowledgeServiceDBError):
    """Raised when data source is missing required database configuration (e.g., schema/table identifiers)."""


class KnowledgeServiceChunkNotFoundError(KnowledgeServiceDBError):
    """Raised when a chunk cannot be found in the database."""


class KnowledgeServiceChunkAlreadyExistsError(KnowledgeServiceDBError):
    """Raised when attempting to create a chunk that already exists in the database."""


class KnowledgeServiceDBOperationError(KnowledgeServiceDBError):
    """Raised when a database operation fails at runtime (e.g., create/update/delete chunk failures)."""
