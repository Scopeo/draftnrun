import hashlib
import hmac
import logging
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_xor_verify_api_key,
)
from ada_backend.schemas.auth_schema import AuthenticatedEntity
from ada_backend.schemas.git_sync_schemas import (
    GitHubAppInfoResponse,
    GitHubRepoSummary,
    GitSyncConfigResponse,
    GitSyncImportRequest,
    GitSyncImportResponse,
)
from ada_backend.services.git_sync_service import (
    InstallationOwnershipError,
    disconnect_sync,
    get_config,
    handle_github_push,
    import_from_github,
    list_configs_for_organization,
    list_installation_repos_summary,
)
from ada_backend.services.github_client import GithubClientError
from ada_backend.utils.github_state import create_install_state
from settings import settings

webhook_router = APIRouter(tags=["Git Sync"])
org_router = APIRouter(prefix="/organizations", tags=["Git Sync"])
LOGGER = logging.getLogger(__name__)


def _verify_github_signature(body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@webhook_router.post("/webhooks/github", summary="Receive GitHub App webhooks")
async def github_webhook(
    request: Request,
    session: Session = Depends(get_db),
):
    if not settings.GITHUB_APP_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="GitHub App webhook secret not configured")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_github_signature(body, signature, settings.GITHUB_APP_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event")
    if event == "ping":
        return {"status": "pong"}
    if event != "push":
        return {"status": "ignored", "reason": f"event '{event}' not handled"}

    payload = await request.json()

    ref = payload.get("ref", "")
    if not ref.startswith("refs/heads/"):
        return {"status": "ignored", "reason": "not a branch push"}
    branch = ref.removeprefix("refs/heads/")

    repository = payload.get("repository", {})
    owner = repository.get("owner", {}).get("login", "")
    repo_name = repository.get("name", "")
    if not owner or not repo_name:
        raise HTTPException(status_code=400, detail="Missing repository owner or name in payload")

    changed_files: set[str] = set()
    for commit in payload.get("commits", []):
        changed_files.update(commit.get("added", []))
        changed_files.update(commit.get("modified", []))

    commit_sha = payload.get("after", "")
    installation_id = (payload.get("installation") or {}).get("id")

    queued, failed = handle_github_push(
        session, owner, repo_name, branch, changed_files, commit_sha, github_installation_id=installation_id
    )
    if queued == 0 and failed == 0:
        return {"status": "ignored", "reason": "no matching sync configs or no graph changes"}

    if failed > 0:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to enqueue {failed} git sync task(s) ({queued} succeeded)",
        )

    return {"status": "ok", "queued": queued}


@org_router.post(
    "/{organization_id}/git-sync",
    response_model=GitSyncImportResponse,
    summary="Import projects from a GitHub repo",
)
async def create_git_sync(
    organization_id: UUID,
    request: GitSyncImportRequest,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> GitSyncImportResponse:
    imported, skipped = await import_from_github(
        session=session,
        organization_id=organization_id,
        user_id=auth.user_id,
        github_owner=request.github_owner,
        github_repo_name=request.github_repo_name,
        branch=request.branch,
        github_installation_id=request.github_installation_id,
        project_type=request.project_type,
    )
    return GitSyncImportResponse(imported=imported, skipped=skipped)


@org_router.get(
    "/{organization_id}/git-sync",
    response_model=list[GitSyncConfigResponse],
    summary="List git sync configs for organization",
)
def list_git_sync_configs(
    organization_id: UUID,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> list[GitSyncConfigResponse]:
    configs = list_configs_for_organization(session, organization_id)
    return [_to_response(c) for c in configs]


@org_router.get(
    "/{organization_id}/git-sync/github-app",
    response_model=GitHubAppInfoResponse,
    summary="Get GitHub App installation info",
)
def get_github_app_info(
    organization_id: UUID,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
) -> GitHubAppInfoResponse:
    all_configured = all([
        settings.GITHUB_APP_SLUG,
        settings.GITHUB_APP_ID,
        settings.GITHUB_APP_PRIVATE_KEY,
        settings.GITHUB_APP_WEBHOOK_SECRET,
    ])
    if not all_configured:
        return GitHubAppInfoResponse(configured=False)

    base_url = f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new"
    if auth.user_id:
        state = create_install_state(organization_id, auth.user_id)
        install_url = f"{base_url}?{urlencode({'state': state})}"
    else:
        install_url = base_url

    return GitHubAppInfoResponse(configured=True, install_url=install_url)


@org_router.get(
    "/{organization_id}/git-sync/installations/{installation_id}/repos",
    summary="List repos accessible to a GitHub App installation",
)
async def list_repos_for_installation(
    organization_id: UUID,
    installation_id: int,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    state: Annotated[str | None, Query(description="Signed install state from the GitHub App redirect")] = None,
) -> list[GitHubRepoSummary]:
    try:
        return await list_installation_repos_summary(
            session,
            installation_id,
            organization_id,
            user_id=auth.user_id,
            install_state=state,
        )
    except InstallationOwnershipError:
        raise HTTPException(
            status_code=404,
            detail="GitHub installation not found",
        )
    except GithubClientError:
        LOGGER.warning("Failed to list repos for installation %s", installation_id)
        raise HTTPException(status_code=502, detail="Failed to list repositories from GitHub")


@org_router.get(
    "/{organization_id}/git-sync/{config_id}",
    response_model=GitSyncConfigResponse,
    summary="Get a git sync config",
)
def get_git_sync_config(
    organization_id: UUID,
    config_id: UUID,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> GitSyncConfigResponse:
    config = get_config(session, config_id, organization_id)
    return _to_response(config)


@org_router.delete(
    "/{organization_id}/git-sync/{config_id}",
    summary="Disconnect git sync",
)
def delete_git_sync_config(
    organization_id: UUID,
    config_id: UUID,
    auth: Annotated[
        AuthenticatedEntity,
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    disconnect_sync(session, config_id, organization_id)
    return {"success": True, "message": "Git sync disconnected"}


def _to_response(config) -> GitSyncConfigResponse:
    return GitSyncConfigResponse(
        id=config.id,
        organization_id=config.organization_id,
        project_id=config.project_id,
        github_owner=config.github_owner,
        github_repo_name=config.github_repo_name,
        graph_folder=config.graph_folder,
        branch=config.branch,
        github_installation_id=config.github_installation_id,
        last_sync_at=config.last_sync_at,
        last_sync_status=config.last_sync_status,
        last_sync_commit_sha=config.last_sync_commit_sha,
        last_sync_error=config.last_sync_error,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )
