from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

NULL_SHA = "0000000000000000000000000000000000000000"
MIGRATION_PATHSPEC = "ada_backend/database/alembic/versions/*.py"


@dataclass(frozen=True)
class MigrationDiff:
    files: list[str]
    diff_base: str | None
    mode: str


def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)


def _commit_exists(repo: Path, rev: str) -> bool:
    return _run_git(repo, ["cat-file", "-e", f"{rev}^{{commit}}"]).returncode == 0


def _is_ancestor(repo: Path, maybe_ancestor: str, head: str) -> bool:
    return _run_git(repo, ["merge-base", "--is-ancestor", maybe_ancestor, head]).returncode == 0


def _changed_files(repo: Path, diff_args: list[str]) -> list[str]:
    result = _run_git(repo, ["diff", "--name-only", *diff_args, "--", MIGRATION_PATHSPEC])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git diff failed with exit code {result.returncode}")
    return [line for line in result.stdout.splitlines() if line]


def detect_changed_migrations(
    *,
    repo: Path,
    event_name: str,
    before: str | None,
    head: str = "HEAD",
    fallback_base: str = "origin/main",
) -> MigrationDiff:
    normalized_before = before.strip() if before else ""

    if event_name == "push" and normalized_before and normalized_before != NULL_SHA:
        if _commit_exists(repo, normalized_before) and _is_ancestor(repo, normalized_before, head):
            return MigrationDiff(
                files=_changed_files(repo, [normalized_before, head]),
                diff_base=normalized_before,
                mode="before",
            )

        if _commit_exists(repo, fallback_base):
            return MigrationDiff(
                files=_changed_files(repo, [f"{fallback_base}...{head}"]),
                diff_base=fallback_base,
                mode="fallback",
            )

        if _commit_exists(repo, f"{head}~1"):
            return MigrationDiff(
                files=_changed_files(repo, [f"{head}~1", head]),
                diff_base=f"{head}~1",
                mode="head-parent",
            )

        return MigrationDiff(files=[], diff_base=None, mode="empty")

    if _commit_exists(repo, f"{head}~1"):
        return MigrationDiff(
            files=_changed_files(repo, [f"{head}~1", head]),
            diff_base=f"{head}~1",
            mode="head-parent",
        )

    return MigrationDiff(files=[], diff_base=None, mode="empty")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect changed Alembic migration files in CI.")
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--before", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--fallback-base", default="origin/main")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)

    try:
        diff = detect_changed_migrations(
            repo=Path(args.repo),
            event_name=args.event_name,
            before=args.before,
            head=args.head,
            fallback_base=args.fallback_base,
        )
    except RuntimeError as exc:
        print(f"Failed to detect changed migrations: {exc}", file=sys.stderr)
        return 1

    if diff.diff_base:
        print(f"Using migration diff base {diff.diff_base} ({diff.mode})", file=sys.stderr)
    else:
        print("No migration diff base available", file=sys.stderr)

    for file in diff.files:
        print(file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
