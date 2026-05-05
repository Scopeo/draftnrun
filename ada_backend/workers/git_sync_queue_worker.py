import asyncio
import logging
from uuid import UUID

from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories import git_sync_repository
from ada_backend.services.git_sync_service import GitSyncError, sync_graph_from_github, sync_prompts_from_github
from ada_backend.workers.base_queue_worker import BaseQueueWorker
from settings import settings

LOGGER = logging.getLogger(__name__)


class GitSyncQueueWorker(BaseQueueWorker):
    def __init__(self):
        super().__init__(
            queue_name=settings.REDIS_GIT_SYNC_QUEUE_NAME,
            worker_label="git-sync-queue",
            trace_project_name="ada-backend-git-sync-worker",
        )

    def required_payload_keys(self, payload: dict) -> tuple[str, ...]:
        if payload.get("type") == "prompt_sync":
            return ("commit_sha", "organization_id", "github_owner", "github_repo_name", "branch",
                    "installation_id", "prompt_paths")
        return ("commit_sha", "config_id")

    def parse_item_id(self, item_payload: dict):
        if item_payload.get("type") == "prompt_sync":
            org = item_payload.get("organization_id", "")
            owner = item_payload.get("github_owner", "")
            repo = item_payload.get("github_repo_name", "")
            branch = item_payload.get("branch", "")
            sha = item_payload.get("commit_sha", "")
            return f"prompt_sync:{org}:{owner}/{repo}:{branch}:{sha}"
        return UUID(item_payload["config_id"])

    def recover_orphaned_item(self, item_payload: dict) -> None:
        if item_payload.get("type") == "prompt_sync":
            LOGGER.info("[git-sync] Orphan recovery: prompt sync task re-queued")
            return

        config_id = UUID(item_payload["config_id"])
        commit_sha = item_payload.get("commit_sha", "")
        with get_db_session() as session:
            config = git_sync_repository.get_git_sync_config_by_id(session, config_id)
            if not config:
                LOGGER.warning("[git-sync] Orphan recovery: config %s no longer exists, skipping", config_id)
                return
            git_sync_repository.update_sync_status(
                session, config_id=config_id, status="pending_retry", commit_sha=commit_sha or None
            )
            LOGGER.info(
                "[git-sync] Recovered orphaned sync for config %s (commit %s) — marked pending_retry",
                config_id,
                commit_sha[:8] if commit_sha else "unknown",
            )

    def process_payload(self, payload: dict, loop: asyncio.AbstractEventLoop) -> None:
        self._ensure_trace_manager()

        if payload.get("type") == "prompt_sync":
            self._process_prompt_sync(payload, loop)
            return

        self._process_graph_sync(payload, loop)

    def _process_graph_sync(self, payload: dict, loop: asyncio.AbstractEventLoop) -> None:
        config_id_raw = payload.get("config_id")
        if not config_id_raw:
            LOGGER.error("Graph sync payload missing config_id")
            return

        config_id = UUID(config_id_raw)
        commit_sha = payload["commit_sha"]

        try:
            with get_db_session() as session:
                config = git_sync_repository.get_git_sync_config_by_id(session, config_id)
                if not config:
                    LOGGER.warning("Git sync config %s not found, skipping", config_id)
                    return

                async def execute():
                    await sync_graph_from_github(session, config, commit_sha)

                loop.run_until_complete(execute())
                LOGGER.info("Git sync completed for config %s at %s", config_id, commit_sha[:8])
        except GitSyncError as e:
            LOGGER.error("Git sync failed for config %s: %s", config_id, e)
        except Exception as e:
            LOGGER.exception("Unexpected error syncing config %s: %s", config_id, e)

    def _process_prompt_sync(self, payload: dict, loop: asyncio.AbstractEventLoop) -> None:
        org_id = UUID(payload["organization_id"])
        github_owner = payload["github_owner"]
        github_repo_name = payload["github_repo_name"]
        branch = payload["branch"]
        installation_id = payload["installation_id"]
        commit_sha = payload["commit_sha"]
        prompt_paths = payload["prompt_paths"]

        try:
            with get_db_session() as session:

                async def execute():
                    await sync_prompts_from_github(
                        session=session,
                        organization_id=org_id,
                        github_owner=github_owner,
                        github_repo_name=github_repo_name,
                        branch=branch,
                        installation_id=installation_id,
                        commit_sha=commit_sha,
                        prompt_paths=prompt_paths,
                    )

                loop.run_until_complete(execute())
                LOGGER.info(
                    "Prompt sync completed for %s/%s at %s — %d file(s)",
                    github_owner, github_repo_name, commit_sha[:8], len(prompt_paths),
                )
        except Exception as e:
            LOGGER.exception(
                "Prompt sync failed for %s/%s at %s: %s",
                github_owner, github_repo_name, commit_sha[:8], e,
            )


_worker = GitSyncQueueWorker()

_request_git_sync_drain = _worker.request_drain
start_git_sync_queue_worker_thread = _worker.start_thread
