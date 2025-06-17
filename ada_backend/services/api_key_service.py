import base64
import secrets
import hashlib
from uuid import UUID

from sqlalchemy.orm import Session
from ada_backend.schemas.auth_schema import (
    ApiKeyCreatedResponse,
    VerifiedApiKey,
    ApiKeyGetResponse,
    ApiKeyData,
)
from ada_backend.repositories.api_key_repository import (
    create_api_key,
    get_api_key_by_hashed_key,
    deactivate_api_key,
    get_api_keys_by_project_id,
    get_project_by_api_key,
)
from settings import settings


API_KEY_PREFIX = "taylor_"
API_KEY_BYTES = 24  # 192 bits of entropy


def _hash_key(key: str) -> str:
    """Create a secure hash of the API key for storage."""
    if settings.BACKEND_SECRET_KEY is None:
        raise ValueError("BACKEND_SECRET_KEY is not set")

    salted = key + settings.BACKEND_SECRET_KEY
    return hashlib.sha256(salted.encode()).hexdigest()


def _generate_api_key() -> str:
    """Generates a random API key string.

    Returns:
        A formatted API key string
    """
    random_bytes = secrets.token_bytes(API_KEY_BYTES)
    base64_key = base64.urlsafe_b64encode(random_bytes).decode().rstrip("=")
    return f"{API_KEY_PREFIX}{base64_key}"


def get_api_keys_service(session: Session, project_id: UUID) -> ApiKeyGetResponse:
    """Service function to get all API keys by project id."""
    api_keys = get_api_keys_by_project_id(session, project_id)
    return ApiKeyGetResponse(
        project_id=project_id,
        api_keys=[ApiKeyData(key_id=key.id, key_name=key.name) for key in api_keys],
    )


def generate_api_key(
    session: Session,
    project_id: UUID,
    key_name: str,
    creator_user_id: UUID,
) -> ApiKeyCreatedResponse:
    """
    Service function to generate a new API key for the given project.
    Returns a user-friendly API key format.
    """
    api_key = _generate_api_key()
    hashed_key = _hash_key(api_key)

    key_id = create_api_key(
        session=session,
        project_id=project_id,
        key_name=key_name,
        hashed_key=hashed_key,
        creator_user_id=creator_user_id,
    )
    return ApiKeyCreatedResponse(
        private_key=api_key,
        key_id=key_id,
    )


def verify_api_key(session: Session, private_key: str) -> VerifiedApiKey:
    """
    Service function to verify an API key.
    """
    try:
        hashed_key = _hash_key(private_key)
    except ValueError as e:
        raise ValueError("Invalid API key") from e

    api_key = get_api_key_by_hashed_key(session, hashed_key=hashed_key)
    if not api_key:
        raise ValueError("Invalid API key")
    if not api_key.is_active:
        raise ValueError("API key is not active")

    project = get_project_by_api_key(session, hashed_key=hashed_key)
    if not project:
        raise ValueError("Project not found for the given API key")
    if project.id != api_key.project_id:
        raise ValueError("Mismatched project ID for the API key")

    return VerifiedApiKey(
        api_key_id=api_key.id,
        project_id=api_key.project_id,
    )


def deactivate_api_key_service(
    session: Session,
    key_id: UUID,
    revoker_user_id: UUID,
) -> UUID:
    """Service function to deactivate an API key."""
    return deactivate_api_key(session, key_id, revoker_user_id)


def verify_ingestion_api_key(
    private_key: str,
) -> str:
    try:
        hashed_key = _hash_key(private_key)
    except ValueError as e:
        raise ValueError("Invalid API key") from e
    return hashed_key
