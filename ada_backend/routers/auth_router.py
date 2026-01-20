import logging
from enum import Enum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ada_backend.context import get_request_context
from ada_backend.database.models import ApiKeyType
from ada_backend.database.setup_db import get_db
from ada_backend.repositories.project_repository import get_project
from ada_backend.schemas.auth_schema import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyDeleteRequest,
    ApiKeyDeleteResponse,
    ApiKeyGetResponse,
    OrgApiKeyCreateRequest,
    SupabaseUser,
    VerifiedApiKey,
)
from ada_backend.services.api_key_service import (
    deactivate_api_key_service,
    generate_scoped_api_key,
    get_api_keys_service,
    verify_api_key,
    verify_ingestion_api_key,
)
from ada_backend.services.user_roles_service import get_user_access_to_organization, is_user_super_admin
from settings import settings
from supabase import Client, create_client

LOGGER = logging.getLogger(__name__)


class UserRights(Enum):
    SUPER_ADMIN = ("super-admin",)
    ADMIN = ("super-admin", "admin")
    DEVELOPER = ("super-admin", "admin", "developer")
    MEMBER = ("super-admin", "admin", "developer", "member")


if not settings.SUPABASE_PROJECT_URL or not settings.SUPABASE_PROJECT_KEY:
    raise ValueError("SUPABASE_PROJECT_URL and SUPABASE_PROJECT_KEY must be set")

supabase: Client = create_client(settings.SUPABASE_PROJECT_URL, settings.SUPABASE_PROJECT_KEY)
bearer = HTTPBearer()
router = APIRouter(prefix="/auth", tags=["Auth"])


# TODO : move to a utils file
async def get_user_from_supabase_token(
    authorization: HTTPAuthorizationCredentials = Depends(bearer),
) -> SupabaseUser:
    """
    Validate Supabase JWT from Authorization header and return user info.
    Also sets the user in the request context.

    Args:
        authorization (Optional[str]): Supabase JWT in the 'Authorization' header.

    Returns:
        SupabaseUser: User information (e.g., user.id, user.email).
    """
    supabase_token = authorization.credentials

    # Bypass authentication in offline mode
    if settings.OFFLINE_MODE:
        user = SupabaseUser(
            id=UUID("11111111-1111-1111-1111-111111111111"), email="dummy@email.com", token="offline-mode-token"
        )
        context = get_request_context()
        context.set_user(user)
        return user

    try:
        user_response = supabase.auth.get_user(supabase_token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid Supabase token")

        user = SupabaseUser(
            id=user_response.user.id,
            email=user_response.user.email,
            token=supabase_token,
        )

        context = get_request_context()
        context.set_user(user)

        return user
    except HTTPException:
        raise
    except Exception as e:
        error_msg = "Failed to validate Supabase token"
        if "expired" in str(e).lower():
            error_msg = "Token has expired"
            LOGGER.error("Supabase token has expired", exc_info=True)
        elif "invalid" in str(e).lower():
            error_msg = "Invalid token format"
            LOGGER.error("Invalid Supabase token format", exc_info=True)
        else:
            LOGGER.error("Failed to validate Supabase token", exc_info=True)

        raise HTTPException(status_code=401, detail=error_msg) from e


# TODO : move to a utils file
def user_has_access_to_project_dependency(allowed_roles: set[str]):
    """
    Dependency that checks if a user has access to a project and returns the user if they do.
    Raises HTTP 403 if the user doesn't have access.
    """

    async def wrapper(
        project_id: UUID,
        user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
        session: Session = Depends(get_db),
    ) -> SupabaseUser:
        try:
            project = get_project(session, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            access = await get_user_access_to_organization(
                user=user,
                organization_id=project.organization_id,
            )

            LOGGER.info(f"User {user.id=} has access to project {project_id=} with role {access.role=}")
            if access.role not in allowed_roles:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have access to this project",
                )
        except ValueError as e:
            LOGGER.error(
                f"Access check failed for user {user.id} on project {project_id}: {e}",
                exc_info=True,
            )
            raise HTTPException(status_code=403, detail="You don't have access to this project") from e
        return user

    return wrapper


# TODO : move to a utils file
def user_has_access_to_organization_dependency(allowed_roles: set[str]):
    """
    Dependency that checks if a user has access to a project and returns the user if they do.
    Raises HTTP 403 if the user doesn't have access.
    """

    async def wrapper(
        organization_id: UUID,
        user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    ) -> SupabaseUser:
        try:
            access = await get_user_access_to_organization(
                user=user,
                organization_id=organization_id,
            )
            LOGGER.info(f"User {user.id=} has access to organization {organization_id=} with role {access.role=}")
            if access.role not in allowed_roles:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have access to this organization",
                )
        except ValueError as e:
            LOGGER.error(
                f"Access check failed for user {user.id} on organization {organization_id}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=403,
                detail="You don't have access to this organization",
            ) from e
        return user

    return wrapper


# TODO : move to a utils file
def ensure_super_admin_dependency():
    async def wrapper(
        user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    ) -> SupabaseUser:
        if not user.id:
            raise HTTPException(status_code=400, detail="User ID not found")
        is_super = await is_user_super_admin(user)
        if not is_super:
            raise HTTPException(status_code=403, detail="Super admin required")
        return user

    return wrapper


@router.get("/api-key", summary="Get API Keys")
async def get_api_keys(
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    project_id: UUID = Query(..., description="The ID of the project to retrieve API keys for"),
) -> ApiKeyGetResponse:
    """
    Get all active API keys for the authenticated user.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_api_keys_service(session, project_id=project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get API keys") from e


@router.post("/api-key", summary="Create API Key")
async def create_api_key(
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
    api_key_create: ApiKeyCreateRequest = Body(...),
) -> ApiKeyCreatedResponse:
    """
    Generate and store a new API key for the authenticated user.
    This API key gives users access to run inferences using an any Agent or Pipeline
    that they have access to (i.e. they are a member of the organization that
    the Agent or Pipeline belongs to)

    Args:
        user (SupabaseUser): User information from Supabase.
        db (Session): Database session.

    Returns:
        ApiKeyCreatedResponse: Generated API key.

    Raises:
        HTTPException: If the API key cannot be created.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    _is_user = user_has_access_to_project_dependency(
        allowed_roles=set(UserRights.DEVELOPER.value),
    )
    # Check if user has access to project. If not, a 403 is raised
    user = await _is_user(project_id=api_key_create.project_id, user=user, session=session)

    try:
        return generate_scoped_api_key(
            session=session,
            scope_type=ApiKeyType.PROJECT.value,
            scope_id=api_key_create.project_id,
            key_name=api_key_create.key_name,
            creator_user_id=user.id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create API key") from e


@router.get("/org-api-key", summary="Get Organization API Keys")
async def get_org_api_keys(
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    organization_id: UUID = Query(..., description="The ID of the organization to retrieve API keys for"),
) -> ApiKeyGetResponse:
    """
    Get all active API keys for the authenticated user.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_api_keys_service(session, organization_id=organization_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get API keys") from e


@router.post("/org-api-key", summary="Create Organization API Key")
async def create_org_api_key(
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
    org_api_key_create: OrgApiKeyCreateRequest = Body(...),
) -> ApiKeyCreatedResponse:
    """
    Generate and store a new organization API key for the authenticated user.
    This API key gives users access to run inferences using an any Agent or Pipeline
    that they have access to (i.e. they are a member of the organization that
    the Agent or Pipeline belongs to)

    Args:
        user (SupabaseUser): User information from Supabase.
        db (Session): Database session.

    Returns:
        ApiKeyCreatedResponse: Generated API key.

    Raises:
        HTTPException: If the API key cannot be created.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    _is_user = user_has_access_to_organization_dependency(
        allowed_roles=set(UserRights.ADMIN.value),
    )
    user = await _is_user(organization_id=org_api_key_create.org_id, user=user)

    try:
        return generate_scoped_api_key(
            session=session,
            scope_type=ApiKeyType.ORGANIZATION.value,
            scope_id=org_api_key_create.org_id,
            key_name=org_api_key_create.key_name,
            creator_user_id=user.id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create Organization API key") from e


@router.delete("/api-key", summary="Delete API Key")
async def delete_api_key_route(
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
    api_key_delete: ApiKeyDeleteRequest = Body(...),
) -> ApiKeyDeleteResponse:
    """
    Delete the API key for the authenticated user.

    Args:
        user (SupabaseUser): User information from Supabase.
        db (Session): Database session.

    Returns:
        ApiKeyDeleteResponse: Success message.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        deactivate_api_key_service(
            session,
            key_id=api_key_delete.key_id,
            revoker_user_id=user.id,
        )

        return ApiKeyDeleteResponse(
            message="API key deleted successfully",
            key_id=api_key_delete.key_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete API key") from e


async def verify_api_key_dependency(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: Session = Depends(get_db),
) -> VerifiedApiKey:
    """
    Dependency to verify an API key from the 'X-API-Key' header.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    cleaned_x_api_key = x_api_key.replace("\\n", "\n").strip('"')

    try:
        return verify_api_key(session, private_key=cleaned_x_api_key)
    except ValueError as e:
        LOGGER.error("API key verification failed", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid API key") from e


def _create_api_key_dependency(header_name: str, expected_hash: str | None, error_detail: str):
    """
    Factory function to create an API key verification dependency.

    Args:
        header_name: Name of the header to read the API key from
        expected_hash: Expected hashed API key value from settings
        error_detail: Error message to return if verification fails
    Returns:
        A FastAPI dependency function that verifies the API key
    """

    async def verify_api_key_dependency(
        api_key: str = Header(..., alias=header_name),
    ) -> None:
        if not expected_hash:
            raise HTTPException(status_code=401, detail=f"{error_detail} (not configured)")
        hashed_key = verify_ingestion_api_key(private_key=api_key)
        if hashed_key != expected_hash:
            raise HTTPException(status_code=401, detail=error_detail)

    return verify_api_key_dependency


# Create API key dependencies using the factory function
verify_ingestion_api_key_dependency = _create_api_key_dependency(
    header_name="X-Ingestion-API-Key",
    expected_hash=settings.INGESTION_API_KEY_HASHED,
    error_detail="Invalid ingestion API key",
)

verify_webhook_api_key_dependency = _create_api_key_dependency(
    header_name="X-Webhook-API-Key",
    expected_hash=settings.WEBHOOK_API_KEY_HASHED,
    error_detail="Invalid webhook API key",
)


async def super_admin_or_admin_api_key_dependency(
    authorization: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    admin_api_key: str | None = Header(None, alias="X-Admin-API-Key"),
) -> None:
    """
    Dependency that allows either super admin user authentication OR admin API key.
    Used for endpoints that require super admin access or admin key authentication (e.g., setting organization limits).
    """

    if authorization and authorization.credentials and admin_api_key:
        LOGGER.exception(
            "User has entered two authenticators :\n"
            f"  - User token (JWT) : {authorization.credentials}\n"
            f"  - Admin API Key : {admin_api_key}"
        )
        raise HTTPException(status_code=400, detail="Provide either Authorization token OR X-Admin-API-Key, not both")

    if admin_api_key:
        hashed_key = verify_ingestion_api_key(private_key=admin_api_key)
        if hashed_key == settings.ADMIN_KEY_HASHED:
            return None
        else:
            raise HTTPException(status_code=401, detail="Invalid admin API key")

    if authorization and authorization.credentials:
        user = await get_user_from_supabase_token(authorization)
        if not user.id:
            raise HTTPException(status_code=401, detail="Invalid super admin token")

        is_super = await is_user_super_admin(user)
        if is_super:
            return None
        else:
            raise HTTPException(status_code=403, detail="You are not a super admin")

    raise HTTPException(
        status_code=403,
        detail="Access denied: requires super admin authentication or valid admin API key",
    )


def user_has_access_to_organization_xor_verify_api_key(allowed_roles: set[str]):
    """
    Factory function that returns a flexible authentication dependency.
    """

    async def wrapper(
        organization_id: UUID,
        authorization: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
        x_api_key: str | None = Header(None, alias="X-API-Key"),
        session: Session = Depends(get_db),
    ) -> tuple[UUID | None, UUID | None]:
        """Flexible authentication: tries user auth first, falls back to API key auth."""

        if authorization and authorization.credentials and x_api_key:
            LOGGER.exception(
                "User has entered two authenticators :\n"
                f"  - User token (JWT) : {authorization.credentials}\n"
                f"  - User token (JWT) is not valid {x_api_key}"
            )
            raise HTTPException(
                status_code=400,
                detail=("Provide either Authorization token OR X-API-Key, not both"),
            )

        if authorization and authorization.credentials:
            try:
                user = await get_user_from_supabase_token(authorization)
                user = await user_has_access_to_organization_dependency(allowed_roles=allowed_roles)(
                    organization_id=organization_id, user=user
                )
                return (user.id, None)
            except HTTPException as e:
                LOGGER.exception(f"User token (JWT) is not valid {e.detail}")
                raise HTTPException(
                    status_code=401,
                    detail=("Authentication failed : User token (JWT) is not valid"),
                ) from e

        if x_api_key:
            try:
                verified_api_key = await verify_api_key_dependency(x_api_key=x_api_key, session=session)
                if verified_api_key.organization_id != organization_id:
                    LOGGER.exception(
                        "API Key is for organization %s => access to organization %s denied",
                        verified_api_key.organization_id,
                        organization_id,
                    )
                    raise HTTPException(status_code=403, detail="You don't have access to this organization")
                return (None, verified_api_key.api_key_id)
            except HTTPException as e:
                LOGGER.exception(f"API Key is not valid : {e.detail}")
                raise HTTPException(
                    status_code=401,
                    detail=("Authentication failed : API Key is not valid"),
                ) from e

        LOGGER.exception("No authentication provided for organization access")
        raise HTTPException(
            status_code=401,
            detail="Authentication required: provide either Authorization token or X-API-Key header",
        )

    return wrapper
