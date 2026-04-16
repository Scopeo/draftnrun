import json
import logging
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ProjectType
from ada_backend.mixpanel_analytics import track_deployed_to_production
from ada_backend.repositories import git_sync_repository
from ada_backend.repositories.graph_runner_repository import (
    insert_graph_runner_and_bind_to_project,
)
from ada_backend.schemas.git_sync_schemas import GitSyncImportResult
from ada_backend.schemas.pipeline.graph_schema import GraphSaveV2Schema, GraphUpdateSchema
from ada_backend.services import github_client
from ada_backend.services.graph.deploy_graph_service import deploy_graph_service
from ada_backend.services.graph.graph_v2_mapper_service import graph_save_v2_to_graph_update
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.services.project_service import create_project_with_graph_runner
from ada_backend.utils.redis_client import push_git_sync_task

LOGGER = logging.getLogger(__name__)


class GitSyncError(Exception):
    pass


class GitSyncConfigNotFound(Exception):
    def __init__(self, config_id: UUID):
        self.config_id = config_id
        super().__init__(f"Git sync config {config_id} not found")


class GraphJsonNotFound(Exception):
    def __init__(self, repo: str, branch: str):
        self.repo = repo
        self.branch = branch
        super().__init__(f"No graph.json found in {repo} on branch {branch}")


async def _fetch_graph_update_payload(config: db.GitSyncConfig, commit_sha: str) -> GraphUpdateSchema:
    graph_path = f"{config.graph_folder}/graph.json" if config.graph_folder else "graph.json"

    raw = await github_client.fetch_file(
        repo=config.github_repo,
        path=graph_path,
        ref=commit_sha,
        installation_id=config.github_installation_id,
    )
    graph_map = json.loads(raw)

    nodes = graph_map.get("nodes", [])
    components = []
    for node in nodes:
        file_key = node.get("file_key")
        if not file_key:
            raise ValueError("Each node in graph.json must define file_key")
        component_path = (
            f"{config.graph_folder}/{file_key}.json"
            if config.graph_folder
            else f"{file_key}.json"
        )
        component_raw = await github_client.fetch_file(
            repo=config.github_repo,
            path=component_path,
            ref=commit_sha,
            installation_id=config.github_installation_id,
        )
        component_data = json.loads(component_raw)
        component_data["file_key"] = file_key
        components.append(component_data)

    payload_v2 = GraphSaveV2Schema(graph_map=graph_map, components=components)
    return graph_save_v2_to_graph_update(payload_v2)


async def import_from_github(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
    github_owner: str,
    github_repo_name: str,
    branch: str,
    github_installation_id: int,
    project_type: ProjectType = ProjectType.WORKFLOW,
) -> tuple[list[GitSyncImportResult], list[str]]:
    """Scan a GitHub repo for graph.json files, create a project + sync config for each.

    Returns (imported, skipped) where imported is a list of typed import results,
    and skipped is a list of folder names that already had a sync config.
    """
    github_repo = f"{github_owner}/{github_repo_name}"
    head_sha = await github_client.get_branch_head_sha(github_repo, branch, github_installation_id)
    github_folders = await github_client.find_graph_json_folders(
        github_repo, ref=head_sha, installation_id=github_installation_id
    )

    if not github_folders:
        raise GraphJsonNotFound(github_repo, branch)

    existing_configs = git_sync_repository.get_configs_by_repo_and_branch(
        session, github_owner, github_repo_name, branch, github_installation_id=github_installation_id
    )
    existing_folders = {existing_config.graph_folder for existing_config in existing_configs}

    imported: list[GitSyncImportResult] = []
    skipped: list[str] = []

    for github_folder in github_folders:
        if github_folder in existing_folders:
            skipped.append(github_folder)
            continue

        project_name = github_folder if github_folder else github_repo_name
        project_id = uuid4()

        project, _graph_runner_id = create_project_with_graph_runner(
            session=session,
            organization_id=organization_id,
            project_id=project_id,
            project_name=project_name,
            description=f"Imported from GitHub {github_repo} from folder {github_folder}"
            if github_folder
            else f"Imported from GitHub {github_repo}",
            project_type=project_type,
            template=None,
            graph_id=uuid4(),
            add_input=True,
        )

        try:
            config = git_sync_repository.create_git_sync_config(
                session=session,
                organization_id=organization_id,
                project_id=project.id,
                github_owner=github_owner,
                github_repo_name=github_repo_name,
                graph_folder=github_folder,
                branch=branch,
                github_installation_id=github_installation_id,
                created_by_user_id=user_id,
            )
        except IntegrityError:
            session.rollback()
            LOGGER.warning("Sync config already exists for folder %r in %s — skipping", github_folder, github_repo)
            skipped.append(github_folder)
            continue

        await _enqueue_initial_sync(config)

        imported.append(
            GitSyncImportResult(
                graph_folder=github_folder,
                project_id=project.id,
                project_name=project_name,
                config_id=config.id,
                status="created",
            )
        )

    LOGGER.info(
        "Imported %d project(s) from %s (branch %s), skipped %d already-linked folder(s)",
        len(imported),
        github_repo,
        branch,
        len(skipped),
    )

    return imported, skipped


async def _enqueue_initial_sync(config: db.GitSyncConfig) -> None:
    try:
        head_sha = await github_client.get_branch_head_sha(
            repo=config.github_repo,
            branch=config.branch,
            installation_id=config.github_installation_id,
        )
    except Exception:
        LOGGER.warning(
            "Could not fetch HEAD SHA for initial sync of config %s — skipping initial sync",
            config.id,
            exc_info=True,
        )
        return

    if not push_git_sync_task(config.id, head_sha):
        LOGGER.warning("Failed to enqueue initial sync task for config %s", config.id)


async def sync_graph_from_github(
    session: Session,
    config: db.GitSyncConfig,
    commit_sha: str,
) -> None:
    try:
        graph_data = await _fetch_graph_update_payload(config, commit_sha)
    except Exception as e:
        LOGGER.error(
            "Failed to fetch graph payload from %s at %s: %s",
            config.github_repo,
            commit_sha,
            e,
        )
        git_sync_repository.update_sync_status(
            session=session, config_id=config.id, status="fetch_failed", commit_sha=commit_sha,
            error_message=str(e),
        )
        raise GitSyncError(f"Failed to fetch graph from GitHub: {e}") from e

    new_runner_id = uuid4()
    try:
        insert_graph_runner_and_bind_to_project(session, new_runner_id, project_id=config.project_id, env=None)
        await update_graph_service(
            session=session,
            graph_runner_id=new_runner_id,
            project_id=config.project_id,
            graph_project=graph_data,
            user_id=config.created_by_user_id,
            bypass_validation=True,
            skip_validation=True,
        )
    except Exception as e:
        LOGGER.error("Failed to build graph runner for project %s: %s", config.project_id, e)
        git_sync_repository.update_sync_status(
            session=session, config_id=config.id, status="update_failed", commit_sha=commit_sha,
            error_message=str(e),
        )
        raise GitSyncError(f"Graph update failed: {e}") from e

    try:
        deploy_graph_service(
            session=session,
            graph_runner_id=new_runner_id,
            project_id=config.project_id,
        )
    except Exception as e:
        LOGGER.error("Failed to deploy graph for project %s: %s", config.project_id, e)
        git_sync_repository.update_sync_status(
            session=session, config_id=config.id, status="deploy_failed", commit_sha=commit_sha,
            error_message=str(e),
        )
        raise GitSyncError(f"Graph deploy failed: {e}") from e

    git_sync_repository.update_sync_status(
        session=session, config_id=config.id, status="success", commit_sha=commit_sha
    )
    track_deployed_to_production(config.created_by_user_id, config.organization_id, config.project_id)

    LOGGER.info(
        "Synced project %s from %s@%s — prod runner: %s",
        config.project_id,
        config.github_repo,
        commit_sha[:8],
        new_runner_id,
    )


def disconnect_sync(
    session: Session,
    config_id: UUID,
    organization_id: UUID,
) -> None:
    config = git_sync_repository.get_git_sync_config_by_id(session, config_id)
    if not config:
        raise GitSyncConfigNotFound(config_id)

    if config.organization_id != organization_id:
        raise GitSyncConfigNotFound(config_id)

    git_sync_repository.delete_git_sync_config(session, config_id)

    LOGGER.info("Disconnected git sync config %s for project %s", config_id, config.project_id)


def handle_github_push(
    session: Session,
    github_owner: str,
    github_repo_name: str,
    branch: str,
    changed_files: set[str],
    commit_sha: str,
    github_installation_id: int | None = None,
) -> tuple[int, int]:
    """Queue git sync tasks for configs whose tracked graph file changed in a push."""
    configs = git_sync_repository.get_configs_by_repo_and_branch(
        session, github_owner, github_repo_name, branch, github_installation_id=github_installation_id
    )
    if not configs:
        return 0, 0

    queued = 0
    failed = 0
    for config in configs:
        if config.graph_folder:
            folder_prefix = f"{config.graph_folder}/"
            if not any(path.startswith(folder_prefix) for path in changed_files):
                continue
        else:
            if not any("/" not in path for path in changed_files):
                continue

        if push_git_sync_task(config.id, commit_sha):
            queued += 1
        else:
            failed += 1
            LOGGER.error("Failed to enqueue git sync task for config %s", config.id)

    return queued, failed


def list_configs_for_organization(
    session: Session,
    organization_id: UUID,
) -> list[db.GitSyncConfig]:
    return git_sync_repository.list_git_sync_configs_by_org(session, organization_id)


def get_config(
    session: Session,
    config_id: UUID,
    organization_id: UUID,
) -> db.GitSyncConfig:
    config = git_sync_repository.get_git_sync_config_by_id(session, config_id)
    if not config or config.organization_id != organization_id:
        raise GitSyncConfigNotFound(config_id)
    return config
