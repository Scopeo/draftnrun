import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def create_git_sync_config(
    session: Session,
    organization_id: UUID,
    project_id: UUID,
    github_owner: str,
    github_repo_name: str,
    graph_folder: str,
    branch: str,
    github_installation_id: int,
    created_by_user_id: UUID | None = None,
) -> db.GitSyncConfig:
    config = db.GitSyncConfig(
        organization_id=organization_id,
        project_id=project_id,
        github_owner=github_owner,
        github_repo_name=github_repo_name,
        graph_folder=graph_folder,
        branch=branch,
        github_installation_id=github_installation_id,
        created_by_user_id=created_by_user_id,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def get_git_sync_config_by_id(session: Session, config_id: UUID) -> db.GitSyncConfig | None:
    return session.query(db.GitSyncConfig).filter(db.GitSyncConfig.id == config_id).first()


def get_git_sync_config_by_project(session: Session, project_id: UUID) -> db.GitSyncConfig | None:
    return session.query(db.GitSyncConfig).filter(db.GitSyncConfig.project_id == project_id).first()


def get_configs_by_repo_and_branch(
    session: Session,
    github_owner: str,
    github_repo_name: str,
    branch: str,
    github_installation_id: int | None = None,
) -> list[db.GitSyncConfig]:
    query = session.query(db.GitSyncConfig).filter(
        db.GitSyncConfig.github_owner == github_owner,
        db.GitSyncConfig.github_repo_name == github_repo_name,
        db.GitSyncConfig.branch == branch,
    )
    if github_installation_id is not None:
        query = query.filter(db.GitSyncConfig.github_installation_id == github_installation_id)
    return query.all()


def list_git_sync_configs_by_org(session: Session, organization_id: UUID) -> list[db.GitSyncConfig]:
    return (
        session.query(db.GitSyncConfig)
        .filter(db.GitSyncConfig.organization_id == organization_id)
        .order_by(db.GitSyncConfig.created_at.desc())
        .all()
    )


def update_sync_status(
    session: Session,
    config_id: UUID,
    status: str,
    commit_sha: str | None = None,
    error_message: str | None = None,
) -> None:
    config = get_git_sync_config_by_id(session, config_id)
    if not config:
        LOGGER.warning("Git sync config not found for id=%s", config_id)
        return
    config.last_sync_at = datetime.now(timezone.utc)
    config.last_sync_status = status
    config.last_sync_error = error_message
    if commit_sha:
        config.last_sync_commit_sha = commit_sha
    session.commit()


def delete_git_sync_config(session: Session, config_id: UUID) -> bool:
    config = get_git_sync_config_by_id(session, config_id)
    if not config:
        return False
    session.delete(config)
    session.commit()
    return True
