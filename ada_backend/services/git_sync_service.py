import json
import logging
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ProjectType
from ada_backend.mixpanel_analytics import track_deployed_to_production
from ada_backend.repositories import git_sync_repository, github_app_installation_repository
from ada_backend.repositories.graph_runner_repository import (
    insert_graph_runner_and_bind_to_project,
)
from ada_backend.repositories.prompt_repository import (
    create_prompt,
    create_prompt_version,
    get_latest_prompt_version,
    get_latest_version_number,
    lock_prompt_for_update,
)
from ada_backend.schemas.git_sync_schemas import GitHubRepoSummary, GitSyncImportResult, GitSyncPromptImportResult
from ada_backend.schemas.pipeline.graph_schema import GraphSaveV2Schema, GraphUpdateSchema
from ada_backend.services import github_client
from ada_backend.services.errors import ServiceError
from ada_backend.services.github_client import PROMPT_LIBRARY_DIR
from ada_backend.services.graph.deploy_graph_service import deploy_graph_service
from ada_backend.services.graph.graph_v2_mapper_service import graph_save_v2_to_graph_update
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.services.project_service import create_project_with_graph_runner
from ada_backend.utils.github_state import verify_install_state
from ada_backend.utils.prompt_markdown import ParsedPromptFile, parse_prompt_markdown
from ada_backend.utils.redis_client import push_git_sync_task, push_prompt_sync_task

LOGGER = logging.getLogger(__name__)


class GitSyncError(Exception):
    pass


class GitSyncConfigNotFound(ServiceError):
    status_code = 404

    def __init__(self, config_id: UUID):
        self.config_id = config_id
        super().__init__(f"Git sync config {config_id} not found")


class DraftnrunFolderNotFound(ServiceError):
    status_code = 422

    def __init__(self, repo: str, branch: str):
        self.repo = repo
        self.branch = branch
        super().__init__(
            f"No draftnrun/ folder found in {repo} on branch {branch}. "
            "The repository must contain a draftnrun/ root with projects/ and/or prompts/ subfolders."
        )


class GraphJsonNotFound(ServiceError):
    status_code = 422

    def __init__(self, repo: str, branch: str):
        self.repo = repo
        self.branch = branch
        super().__init__(f"No graph.json found in draftnrun/projects/ of {repo} on branch {branch}")


class InstallationOwnershipError(ServiceError):
    """Raised when a GitHub installation belongs to a different organization."""

    status_code = 404

    def __init__(self, installation_id: int):
        self.installation_id = installation_id
        super().__init__("GitHub installation not found")


def register_installation_if_new(session: Session, installation_id: int, organization_id: UUID) -> None:
    """Register a GitHub installation for the org, or raise if it belongs to another org."""
    existing = github_app_installation_repository.get_by_installation_id(session, installation_id)
    if existing:
        if existing.organization_id != organization_id:
            raise InstallationOwnershipError(installation_id)
        return
    try:
        github_app_installation_repository.register_installation(session, installation_id, organization_id)
    except IntegrityError:
        session.rollback()
        existing = github_app_installation_repository.get_by_installation_id(session, installation_id)
        if existing is None:
            raise
        if existing.organization_id != organization_id:
            raise InstallationOwnershipError(installation_id)


def ensure_installation_owned(session: Session, installation_id: int, organization_id: UUID) -> None:
    """Assert that *installation_id* is already registered and belongs to *organization_id*.

    Unlike ``register_installation_if_new`` this never auto-registers.
    """
    existing = github_app_installation_repository.get_by_installation_id(session, installation_id)
    if not existing or existing.organization_id != organization_id:
        raise InstallationOwnershipError(installation_id)


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
        component_path = f"{config.graph_folder}/{file_key}.json" if config.graph_folder else f"{file_key}.json"
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
) -> tuple[list[GitSyncImportResult], list[str], list[GitSyncPromptImportResult], list[str]]:
    """Scan a GitHub repo for the ``draftnrun/`` folder structure and import projects + prompts.

    Looks for ``draftnrun/projects/*/graph.json`` for projects and
    ``draftnrun/prompts/**/*.md`` for prompts.

    Returns ``(imported_projects, skipped_projects, imported_prompts, skipped_prompts)``.
    """
    ensure_installation_owned(session, github_installation_id, organization_id)

    github_repo = f"{github_owner}/{github_repo_name}"
    head_sha = await github_client.get_branch_head_sha(github_repo, branch, github_installation_id)

    structure = await github_client.discover_draftnrun_repo(
        github_repo, ref=head_sha, installation_id=github_installation_id
    )

    if structure is None:
        raise DraftnrunFolderNotFound(github_repo, branch)

    if not structure.project_folders and not structure.prompt_files:
        raise GraphJsonNotFound(github_repo, branch)

    imported_projects: list[GitSyncImportResult] = []
    skipped_projects: list[str] = []
    if structure.project_folders:
        imported_projects, skipped_projects = await _import_projects(
            session,
            organization_id,
            user_id,
            github_owner,
            github_repo_name,
            branch,
            github_installation_id,
            project_type,
            structure.project_folders,
            github_repo,
        )

    imported_prompts: list[GitSyncPromptImportResult] = []
    skipped_prompts: list[str] = []
    if structure.prompt_files:
        imported_prompts, skipped_prompts = await _import_prompts(
            session,
            organization_id,
            user_id,
            github_owner,
            github_repo_name,
            branch,
            github_installation_id,
            head_sha,
            structure.prompt_files,
            github_repo,
        )

    return imported_projects, skipped_projects, imported_prompts, skipped_prompts


async def _import_projects(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
    github_owner: str,
    github_repo_name: str,
    branch: str,
    github_installation_id: int,
    project_type: ProjectType,
    github_folders: list[str],
    github_repo: str,
) -> tuple[list[GitSyncImportResult], list[str]]:
    existing_configs = git_sync_repository.get_configs_by_repo_and_branch(
        session, github_owner, github_repo_name, branch, github_installation_id=github_installation_id
    )
    existing_folders = {c.graph_folder for c in existing_configs}

    imported: list[GitSyncImportResult] = []
    skipped: list[str] = []

    for github_folder in github_folders:
        if github_folder in existing_folders:
            skipped.append(github_folder)
            continue

        folder_basename = github_folder.rsplit("/", 1)[-1] if "/" in github_folder else github_folder
        project_name = folder_basename if folder_basename else github_repo_name
        project_id = uuid4()

        project, _graph_runner_id = create_project_with_graph_runner(
            session=session,
            organization_id=organization_id,
            project_id=project_id,
            project_name=project_name,
            description=f"Imported from GitHub {github_repo} ({github_folder})"
            if github_folder
            else f"Imported from GitHub {github_repo}",
            project_type=project_type,
            template=None,
            graph_id=uuid4(),
            add_input=True,
            tags=["github"],
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
        "Imported %d project(s) from %s (branch %s), skipped %d",
        len(imported),
        github_repo,
        branch,
        len(skipped),
    )
    return imported, skipped


async def _import_prompts(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
    github_owner: str,
    github_repo_name: str,
    branch: str,
    github_installation_id: int,
    head_sha: str,
    prompt_files: list[str],
    github_repo: str,
) -> tuple[list[GitSyncPromptImportResult], list[str]]:
    existing_mappings = git_sync_repository.get_prompt_mappings_by_repo_and_branch(
        session, organization_id, github_owner, github_repo_name, branch
    )
    existing_paths = {m.prompt_file_path for m in existing_mappings}

    imported: list[GitSyncPromptImportResult] = []
    skipped: list[str] = []

    for file_path in prompt_files:
        if file_path in existing_paths:
            skipped.append(file_path)
            continue

        full_path = f"{PROMPT_LIBRARY_DIR}/{file_path}"
        try:
            raw = await github_client.fetch_file(
                repo=github_repo,
                path=full_path,
                ref=head_sha,
                installation_id=github_installation_id,
            )
        except Exception:
            LOGGER.warning("Failed to fetch prompt file %s from %s — skipping", full_path, github_repo, exc_info=True)
            skipped.append(file_path)
            continue

        parsed = parse_prompt_markdown(raw, file_path)

        try:
            with session.begin_nested():
                prompt_def = create_prompt(session, db.PromptDefinition(organization_id=organization_id))
                create_prompt_version(
                    session,
                    db.PromptVersion(
                        prompt_id=prompt_def.id,
                        version_number=1,
                        name=parsed.name,
                        description=parsed.description,
                        content=parsed.content,
                        created_by=user_id,
                        change_description="Initial import from GitHub",
                    ),
                )
                git_sync_repository.create_prompt_mapping(
                    session=session,
                    organization_id=organization_id,
                    prompt_definition_id=prompt_def.id,
                    github_owner=github_owner,
                    github_repo_name=github_repo_name,
                    branch=branch,
                    prompt_file_path=file_path,
                    github_installation_id=github_installation_id,
                    commit_sha=head_sha,
                )
        except IntegrityError:
            LOGGER.warning("Prompt mapping already exists for %r — skipping", file_path)
            skipped.append(file_path)
            continue

        session.commit()

        imported.append(
            GitSyncPromptImportResult(
                prompt_file_path=file_path,
                prompt_id=prompt_def.id,
                prompt_name=parsed.name,
                status="created",
            )
        )

    LOGGER.info(
        "Imported %d prompt(s) from %s (branch %s), skipped %d",
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
            session=session,
            config_id=config.id,
            status="fetch_failed",
            commit_sha=commit_sha,
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
            session=session,
            config_id=config.id,
            status="update_failed",
            commit_sha=commit_sha,
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
            session=session,
            config_id=config.id,
            status="deploy_failed",
            commit_sha=commit_sha,
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


def _collect_changed_prompt_paths(changed_files: set[str]) -> set[str]:
    """Extract prompt file paths (relative to prompts/) from changed file set."""
    prefix = f"{PROMPT_LIBRARY_DIR}/"
    result: set[str] = set()
    for path in changed_files:
        if path.startswith(prefix) and path.endswith(".md"):
            result.add(path[len(prefix) :])
    return result


def handle_github_push(
    session: Session,
    github_owner: str,
    github_repo_name: str,
    branch: str,
    changed_files: set[str],
    commit_sha: str,
    github_installation_id: int | None = None,
) -> tuple[int, int]:
    """Queue git sync tasks for configs whose tracked graph file changed in a push.

    Also enqueues prompt sync tasks when files under ``draftnrun/prompts/`` changed.
    """
    queued = 0
    failed = 0

    configs = git_sync_repository.get_configs_by_repo_and_branch(
        session, github_owner, github_repo_name, branch, github_installation_id=github_installation_id
    )
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

    changed_prompts = _collect_changed_prompt_paths(changed_files)
    if changed_prompts:
        org_ids = {c.organization_id for c in configs}
        for org_id in org_ids:
            mappings = git_sync_repository.get_prompt_mappings_by_repo_and_branch(
                session, org_id, github_owner, github_repo_name, branch
            )
            mapped_paths = {m.prompt_file_path for m in mappings}
            paths_to_sync = changed_prompts & mapped_paths
            new_paths = changed_prompts - mapped_paths
            if not paths_to_sync and not new_paths:
                continue

            installation_id = github_installation_id
            if installation_id is None:
                if mappings:
                    installation_id = mappings[0].github_installation_id
                else:
                    org_configs = [c for c in configs if c.organization_id == org_id]
                    installation_id = org_configs[0].github_installation_id if org_configs else None

            if installation_id is None:
                continue

            all_paths = sorted(paths_to_sync | new_paths)
            if push_prompt_sync_task(
                organization_id=org_id,
                github_owner=github_owner,
                github_repo_name=github_repo_name,
                branch=branch,
                installation_id=installation_id,
                commit_sha=commit_sha,
                prompt_paths=all_paths,
            ):
                queued += 1
            else:
                failed += 1
                LOGGER.error(
                    "Failed to enqueue prompt sync task for %s/%s org=%s",
                    github_owner,
                    github_repo_name,
                    org_id,
                )

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


async def sync_prompts_from_github(
    session: Session,
    organization_id: UUID,
    github_owner: str,
    github_repo_name: str,
    branch: str,
    installation_id: int,
    commit_sha: str,
    prompt_paths: list[str],
) -> None:
    """Fetch changed prompt files from GitHub and create new versions (or new prompts)."""
    github_repo = f"{github_owner}/{github_repo_name}"
    existing_mappings = git_sync_repository.get_prompt_mappings_by_repo_and_branch(
        session, organization_id, github_owner, github_repo_name, branch
    )
    path_to_mapping = {m.prompt_file_path: m for m in existing_mappings}

    for file_path in prompt_paths:
        full_path = f"{PROMPT_LIBRARY_DIR}/{file_path}"
        try:
            raw = await github_client.fetch_file(
                repo=github_repo,
                path=full_path,
                ref=commit_sha,
                installation_id=installation_id,
            )
        except Exception:
            LOGGER.warning(
                "Failed to fetch prompt %s from %s@%s — skipping",
                full_path,
                github_repo,
                commit_sha[:8],
                exc_info=True,
            )
            continue

        parsed = parse_prompt_markdown(raw, file_path)
        mapping = path_to_mapping.get(file_path)

        if mapping:
            _sync_existing_prompt(session, mapping, parsed, commit_sha)
        else:
            _sync_new_prompt(
                session,
                organization_id,
                github_owner,
                github_repo_name,
                branch,
                installation_id,
                file_path,
                parsed,
                commit_sha,
            )

    session.commit()
    LOGGER.info("Prompt sync completed for %s@%s — %d file(s)", github_repo, commit_sha[:8], len(prompt_paths))


def _sync_existing_prompt(
    session: Session,
    mapping: db.GitSyncPromptMapping,
    parsed: ParsedPromptFile,
    commit_sha: str,
) -> None:
    prompt = lock_prompt_for_update(session, mapping.prompt_definition_id)
    if not prompt:
        LOGGER.warning("Prompt %s referenced by mapping %s no longer exists", mapping.prompt_definition_id, mapping.id)
        return

    latest = get_latest_prompt_version(session, prompt.id)
    if (
        latest
        and latest.content == parsed.content
        and latest.name == parsed.name
        and latest.description == parsed.description
    ):
        git_sync_repository.update_prompt_mapping_sync(session, mapping.id, commit_sha)
        return

    next_version = get_latest_version_number(session, prompt.id) + 1
    create_prompt_version(
        session,
        db.PromptVersion(
            prompt_id=prompt.id,
            version_number=next_version,
            name=parsed.name,
            description=parsed.description,
            content=parsed.content,
            change_description=f"Synced from GitHub ({commit_sha[:8]})",
        ),
    )
    git_sync_repository.update_prompt_mapping_sync(session, mapping.id, commit_sha)
    LOGGER.info("Created version %d for prompt %s from git sync", next_version, prompt.id)


def _sync_new_prompt(
    session: Session,
    organization_id: UUID,
    github_owner: str,
    github_repo_name: str,
    branch: str,
    installation_id: int,
    file_path: str,
    parsed: ParsedPromptFile,
    commit_sha: str,
) -> None:
    try:
        with session.begin_nested():
            prompt_def = create_prompt(session, db.PromptDefinition(organization_id=organization_id))
            create_prompt_version(
                session,
                db.PromptVersion(
                    prompt_id=prompt_def.id,
                    version_number=1,
                    name=parsed.name,
                    description=parsed.description,
                    content=parsed.content,
                    change_description=f"Discovered in GitHub ({commit_sha[:8]})",
                ),
            )
            git_sync_repository.create_prompt_mapping(
                session=session,
                organization_id=organization_id,
                prompt_definition_id=prompt_def.id,
                github_owner=github_owner,
                github_repo_name=github_repo_name,
                branch=branch,
                prompt_file_path=file_path,
                github_installation_id=installation_id,
                commit_sha=commit_sha,
            )
    except IntegrityError:
        LOGGER.warning("Prompt mapping race for %r — skipping", file_path)
        return

    LOGGER.info("Created new prompt %s from git file %s", prompt_def.id, file_path)


async def list_installation_repos_summary(
    session: Session,
    installation_id: int,
    organization_id: UUID,
    user_id: UUID,
    install_state: str | None = None,
) -> list[GitHubRepoSummary]:
    """List repos accessible to a GitHub App installation, returning only the fields the front-end needs.

    On first call for a new installation the caller must supply a valid *install_state*
    token (produced by the ``/github-app`` endpoint) so we can prove the org/user that
    initiated the GitHub App install flow is the same one registering the installation.

    Raises InstallationOwnershipError if the installation belongs to another org or if
    state validation fails for a new installation.
    """
    existing = github_app_installation_repository.get_by_installation_id(session, installation_id)
    if existing:
        if existing.organization_id != organization_id:
            raise InstallationOwnershipError(installation_id)
    else:
        if not install_state:
            LOGGER.warning("Missing install state for new installation %s (org %s)", installation_id, organization_id)
            raise InstallationOwnershipError(installation_id)
        try:
            verify_install_state(install_state, organization_id, user_id)
        except ValueError:
            LOGGER.warning("Invalid install state for installation %s (org %s)", installation_id, organization_id)
            raise InstallationOwnershipError(installation_id)
        register_installation_if_new(session, installation_id, organization_id)

    repos = await github_client.list_installation_repos(installation_id)
    return [
        GitHubRepoSummary(
            full_name=r.get("full_name", ""),
            name=r.get("name", ""),
            owner=r.get("owner", {}).get("login", ""),
            default_branch=r.get("default_branch", "main"),
            private=r.get("private", False),
        )
        for r in repos
    ]
