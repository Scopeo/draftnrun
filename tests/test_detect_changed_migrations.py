from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.detect_changed_migrations import detect_changed_migrations

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git executable is required")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write(repo: Path, relative_path: str, content: str = "revision = 'abc'\ndown_revision = None\n") -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    _write(repo, "README.md", "test\n")
    _commit(repo, "initial")
    return repo


def test_normal_push_uses_before_as_diff_base(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write(repo, "ada_backend/database/alembic/versions/old.py")
    before = _commit(repo, "old migration")

    _write(repo, "ada_backend/database/alembic/versions/new.py")
    _commit(repo, "new migration")
    diff = detect_changed_migrations(repo=repo, event_name="push", before=before)

    assert diff.mode == "before"
    assert diff.diff_base == before
    assert diff.files == ["ada_backend/database/alembic/versions/new.py"]


def test_force_push_non_ancestor_before_falls_back(tmp_path: Path):
    repo = _init_repo(tmp_path)
    fallback_base = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-b", "old-staging")
    _write(repo, "ada_backend/database/alembic/versions/old_branch.py")
    old_before = _commit(repo, "old staging migration")

    _git(repo, "checkout", "main")
    _write(repo, "ada_backend/database/alembic/versions/new_branch.py")
    _commit(repo, "new staging migration")
    diff = detect_changed_migrations(
        repo=repo,
        event_name="push",
        before=old_before,
        fallback_base=fallback_base,
    )

    assert diff.mode == "fallback"
    assert diff.diff_base == fallback_base
    assert diff.files == ["ada_backend/database/alembic/versions/new_branch.py"]


def test_missing_before_object_falls_back_without_bad_object(tmp_path: Path):
    repo = _init_repo(tmp_path)
    fallback_base = _git(repo, "rev-parse", "HEAD")
    missing_before = "2ed6379291ccf8594877885269b827a6f4b7fa5a"

    _write(repo, "ada_backend/database/alembic/versions/new_branch.py")
    _commit(repo, "new staging migration")
    diff = detect_changed_migrations(
        repo=repo,
        event_name="push",
        before=missing_before,
        fallback_base=fallback_base,
    )

    assert diff.mode == "fallback"
    assert diff.files == ["ada_backend/database/alembic/versions/new_branch.py"]


def test_null_before_falls_back_to_branch_diff(tmp_path: Path):
    repo = _init_repo(tmp_path)
    fallback_base = _git(repo, "rev-parse", "HEAD")

    _write(repo, "ada_backend/database/alembic/versions/first_branch.py")
    _commit(repo, "first branch migration")
    _write(repo, "ada_backend/database/alembic/versions/second_branch.py")
    _commit(repo, "second branch migration")
    diff = detect_changed_migrations(
        repo=repo,
        event_name="push",
        before="0000000000000000000000000000000000000000",
        fallback_base=fallback_base,
    )

    assert diff.mode == "fallback"
    assert diff.diff_base == fallback_base
    assert diff.files == [
        "ada_backend/database/alembic/versions/first_branch.py",
        "ada_backend/database/alembic/versions/second_branch.py",
    ]
