from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from ada_backend.services.git_sync_service import (
    handle_github_push,
    import_from_github,
    sync_prompts_from_github,
)
from ada_backend.services.github_client import DraftnrunRepoStructure

PATCH_ENSURE_OWNED = "ada_backend.services.git_sync_service.ensure_installation_owned"


class TestDiscoverDraftnrunRepo:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_draftnrun_folder(self):
        from ada_backend.services.github_client import discover_draftnrun_repo

        with (
            patch(
                "ada_backend.services.github_client.get_installation_token",
                new_callable=AsyncMock,
                return_value="token",
            ),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "tree": [
                    {"type": "blob", "path": "README.md"},
                    {"type": "blob", "path": "src/main.py"},
                ]
            }
            mock_resp.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await discover_draftnrun_repo("owner/repo", "abc123", 42)

        assert result is None

    @pytest.mark.asyncio
    async def test_discovers_projects_and_prompts(self):
        from ada_backend.services.github_client import discover_draftnrun_repo

        with (
            patch(
                "ada_backend.services.github_client.get_installation_token",
                new_callable=AsyncMock,
                return_value="token",
            ),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "tree": [
                    {"type": "blob", "path": "draftnrun/projects/agent-a/graph.json"},
                    {"type": "blob", "path": "draftnrun/projects/agent-a/start.json"},
                    {"type": "blob", "path": "draftnrun/projects/agent-b/graph.json"},
                    {"type": "blob", "path": "draftnrun/prompts/system.md"},
                    {"type": "blob", "path": "draftnrun/prompts/tools/search.md"},
                    {"type": "blob", "path": "draftnrun/prompts/README.txt"},
                ]
            }
            mock_resp.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await discover_draftnrun_repo("owner/repo", "abc123", 42)

        assert result is not None
        assert result.project_folders == [
            "draftnrun/projects/agent-a",
            "draftnrun/projects/agent-b",
        ]
        assert result.prompt_files == ["system.md", "tools/search.md"]


class TestImportFromGithubWithDraftnrun:
    @pytest.mark.asyncio
    async def test_imports_projects_and_prompts(self):
        session = MagicMock()
        org_id = uuid4()
        user_id = uuid4()
        project_id = uuid4()
        config_id = uuid4()
        prompt_id = uuid4()

        project = SimpleNamespace(id=project_id, name="agent-a", organization_id=org_id)
        config = SimpleNamespace(
            id=config_id,
            organization_id=org_id,
            project_id=project_id,
            github_owner="owner",
            github_repo_name="repo",
            graph_folder="draftnrun/projects/agent-a",
            branch="main",
            github_installation_id=42,
            github_repo="owner/repo",
            created_by_user_id=user_id,
        )

        prompt_def = SimpleNamespace(id=prompt_id, organization_id=org_id)

        with (
            patch(PATCH_ENSURE_OWNED),
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.discover_draftnrun_repo",
                new_callable=AsyncMock,
                return_value=DraftnrunRepoStructure(
                    project_folders=["draftnrun/projects/agent-a"],
                    prompt_files=["system.md"],
                ),
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_project_with_graph_runner",
                return_value=(project, uuid4()),
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_git_sync_config",
                return_value=config,
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                return_value=True,
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value="---\ndescription: System prompt\n---\n\nYou are a helpful assistant.",
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_prompt",
                return_value=prompt_def,
            ),
            patch("ada_backend.services.git_sync_service.create_prompt_version"),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_prompt_mapping",
            ),
        ):
            imported_projects, skipped_projects, imported_prompts, skipped_prompts = await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=user_id,
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
            )

        assert len(imported_projects) == 1
        assert imported_projects[0].graph_folder == "draftnrun/projects/agent-a"
        assert len(imported_prompts) == 1
        assert imported_prompts[0].prompt_name == "system"
        assert imported_prompts[0].status == "created"


class TestImportPromptsSkipsOnFetchFailure:
    @pytest.mark.asyncio
    async def test_fetch_failure_appends_to_skipped_prompts(self):
        session = MagicMock()
        org_id = uuid4()
        user_id = uuid4()
        project_id = uuid4()
        config_id = uuid4()

        project = SimpleNamespace(id=project_id, name="agent-a", organization_id=org_id)
        config = SimpleNamespace(
            id=config_id,
            organization_id=org_id,
            project_id=project_id,
            github_owner="owner",
            github_repo_name="repo",
            graph_folder="draftnrun/projects/agent-a",
            branch="main",
            github_installation_id=42,
            github_repo="owner/repo",
            created_by_user_id=user_id,
        )

        with (
            patch(PATCH_ENSURE_OWNED),
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.discover_draftnrun_repo",
                new_callable=AsyncMock,
                return_value=DraftnrunRepoStructure(
                    project_folders=["draftnrun/projects/agent-a"],
                    prompt_files=["good.md", "bad.md"],
                ),
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_project_with_graph_runner",
                return_value=(project, uuid4()),
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_git_sync_config",
                return_value=config,
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                return_value=True,
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                side_effect=lambda repo, path, ref, installation_id: (
                    (_ for _ in ()).throw(RuntimeError("GitHub 500"))
                    if "bad.md" in path
                    else "Good content"
                ),
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_prompt",
                return_value=SimpleNamespace(id=uuid4(), organization_id=org_id),
            ),
            patch("ada_backend.services.git_sync_service.create_prompt_version"),
            patch("ada_backend.services.git_sync_service.git_sync_repository.create_prompt_mapping"),
        ):
            _, _, imported_prompts, skipped_prompts = await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=user_id,
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
            )

        assert "bad.md" in skipped_prompts
        assert len(imported_prompts) == 1


class TestHandleGithubPushWithPrompts:
    def test_enqueues_prompt_sync_for_changed_prompts(self):
        session = MagicMock()
        org_id = uuid4()
        config = SimpleNamespace(
            id=uuid4(),
            graph_folder="draftnrun/projects/agent-a",
            organization_id=org_id,
            github_installation_id=42,
        )
        mapping = SimpleNamespace(
            id=uuid4(),
            organization_id=org_id,
            prompt_definition_id=uuid4(),
            github_owner="owner",
            github_repo_name="repo",
            branch="main",
            prompt_file_path="system.md",
            github_installation_id=42,
        )

        with (
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[config],
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[mapping],
            ),
            patch(
                "ada_backend.services.git_sync_service.push_prompt_sync_task",
                return_value=True,
            ) as push_mock,
        ):
            queued, failed = handle_github_push(
                session,
                "owner",
                "repo",
                "main",
                changed_files={"draftnrun/prompts/system.md"},
                commit_sha="abc123",
                github_installation_id=42,
            )

        assert queued == 1
        assert failed == 0
        push_mock.assert_called_once()
        call_kwargs = push_mock.call_args[1]
        assert call_kwargs["prompt_paths"] == ["system.md"]

    def test_ignores_non_md_files_in_prompts_folder(self):
        session = MagicMock()

        with (
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[],
            ),
        ):
            queued, failed = handle_github_push(
                session,
                "owner",
                "repo",
                "main",
                changed_files={"draftnrun/prompts/README.txt"},
                commit_sha="abc123",
            )

        assert queued == 0
        assert failed == 0

    def test_handles_both_project_and_prompt_changes(self):
        session = MagicMock()
        org_id = uuid4()
        config = SimpleNamespace(
            id=uuid4(),
            graph_folder="draftnrun/projects/agent-a",
            organization_id=org_id,
        )
        mapping = SimpleNamespace(
            id=uuid4(),
            organization_id=org_id,
            prompt_file_path="system.md",
            github_installation_id=42,
        )

        with (
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[config],
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                return_value=True,
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[mapping],
            ),
            patch(
                "ada_backend.services.git_sync_service.push_prompt_sync_task",
                return_value=True,
            ),
        ):
            queued, failed = handle_github_push(
                session,
                "owner",
                "repo",
                "main",
                changed_files={
                    "draftnrun/projects/agent-a/graph.json",
                    "draftnrun/prompts/system.md",
                },
                commit_sha="abc123",
                github_installation_id=42,
            )

        assert queued == 2
        assert failed == 0


class TestSyncPromptsFromGithub:
    @pytest.mark.asyncio
    async def test_creates_new_version_for_existing_prompt(self):
        session = MagicMock()
        org_id = uuid4()
        prompt_id = uuid4()
        mapping = SimpleNamespace(
            id=uuid4(),
            organization_id=org_id,
            prompt_definition_id=prompt_id,
            prompt_file_path="system.md",
        )
        prompt_def = SimpleNamespace(id=prompt_id, organization_id=org_id)
        latest_version = SimpleNamespace(
            id=uuid4(),
            prompt_id=prompt_id,
            version_number=1,
            name="system",
            description="Old description",
            content="Old content",
        )

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value="New content",
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[mapping],
            ),
            patch(
                "ada_backend.services.git_sync_service.lock_prompt_for_update",
                return_value=prompt_def,
            ),
            patch(
                "ada_backend.services.git_sync_service.get_latest_prompt_version",
                return_value=latest_version,
            ),
            patch(
                "ada_backend.services.git_sync_service.get_latest_version_number",
                return_value=1,
            ),
            patch(
                "ada_backend.services.git_sync_service.create_prompt_version",
            ) as create_version_mock,
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.update_prompt_mapping_sync",
            ),
        ):
            await sync_prompts_from_github(
                session=session,
                organization_id=org_id,
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                installation_id=42,
                commit_sha="abc12345",
                prompt_paths=["system.md"],
            )

        create_version_mock.assert_called_once()
        version_obj = create_version_mock.call_args[1] if create_version_mock.call_args[1] else None
        if version_obj is None:
            version_arg = create_version_mock.call_args[0][1]
            assert version_arg.version_number == 2
            assert version_arg.content == "New content"

    @pytest.mark.asyncio
    async def test_skips_version_if_content_unchanged(self):
        session = MagicMock()
        org_id = uuid4()
        prompt_id = uuid4()
        mapping = SimpleNamespace(
            id=uuid4(),
            organization_id=org_id,
            prompt_definition_id=prompt_id,
            prompt_file_path="system.md",
        )
        prompt_def = SimpleNamespace(id=prompt_id, organization_id=org_id)
        latest_version = SimpleNamespace(
            id=uuid4(),
            prompt_id=prompt_id,
            version_number=1,
            name="system",
            description=None,
            content="Same content",
        )

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value="Same content",
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[mapping],
            ),
            patch(
                "ada_backend.services.git_sync_service.lock_prompt_for_update",
                return_value=prompt_def,
            ),
            patch(
                "ada_backend.services.git_sync_service.get_latest_prompt_version",
                return_value=latest_version,
            ),
            patch(
                "ada_backend.services.git_sync_service.create_prompt_version",
            ) as create_version_mock,
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.update_prompt_mapping_sync",
            ),
        ):
            await sync_prompts_from_github(
                session=session,
                organization_id=org_id,
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                installation_id=42,
                commit_sha="abc12345",
                prompt_paths=["system.md"],
            )

        create_version_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_new_prompt_for_unknown_file(self):
        session = MagicMock()
        org_id = uuid4()
        new_prompt_id = uuid4()
        prompt_def = SimpleNamespace(id=new_prompt_id, organization_id=org_id)

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value="---\ndescription: New prompt\n---\n\nHello world.",
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_prompt",
                return_value=prompt_def,
            ) as create_prompt_mock,
            patch(
                "ada_backend.services.git_sync_service.create_prompt_version",
            ) as create_version_mock,
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_prompt_mapping",
            ) as create_mapping_mock,
        ):
            await sync_prompts_from_github(
                session=session,
                organization_id=org_id,
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                installation_id=42,
                commit_sha="abc12345",
                prompt_paths=["new-prompt.md"],
            )

        create_prompt_mock.assert_called_once()
        create_version_mock.assert_called_once()
        version_arg = create_version_mock.call_args[0][1]
        assert version_arg.version_number == 1
        assert version_arg.name == "new-prompt"
        assert version_arg.description == "New prompt"
        assert version_arg.content == "Hello world."
        create_mapping_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_integrity_error_uses_savepoint_not_full_rollback(self):
        session = MagicMock()
        org_id = uuid4()
        prompt_id_ok = uuid4()
        prompt_id_dup = uuid4()
        prompt_def_ok = SimpleNamespace(id=prompt_id_ok, organization_id=org_id)
        prompt_def_dup = SimpleNamespace(id=prompt_id_dup, organization_id=org_id)
        existing_mapping = SimpleNamespace(
            id=uuid4(),
            organization_id=org_id,
            prompt_definition_id=uuid4(),
            prompt_file_path="existing.md",
        )
        existing_prompt = SimpleNamespace(id=existing_mapping.prompt_definition_id, organization_id=org_id)
        existing_version = SimpleNamespace(
            id=uuid4(),
            prompt_id=existing_mapping.prompt_definition_id,
            version_number=1,
            name="existing",
            description="Old description",
            content="Old content",
        )

        call_count = 0

        def create_mapping_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("prompt_file_path") == "dup.md":
                raise IntegrityError("duplicate", {}, None)

        prompt_defs = iter([prompt_def_ok, prompt_def_dup])

        async def fetch_side_effect(repo, path, ref, installation_id):
            if "ok.md" in path:
                return "OK content"
            if "dup.md" in path:
                return "Dup content"
            return "Updated existing"

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                side_effect=fetch_side_effect,
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_prompt_mappings_by_repo_and_branch",
                return_value=[existing_mapping],
            ),
            patch(
                "ada_backend.services.git_sync_service.lock_prompt_for_update",
                return_value=existing_prompt,
            ),
            patch(
                "ada_backend.services.git_sync_service.get_latest_prompt_version",
                return_value=existing_version,
            ),
            patch(
                "ada_backend.services.git_sync_service.get_latest_version_number",
                return_value=1,
            ),
            patch(
                "ada_backend.services.git_sync_service.create_prompt",
                side_effect=lambda session, obj: next(prompt_defs),
            ),
            patch("ada_backend.services.git_sync_service.create_prompt_version"),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_prompt_mapping",
                side_effect=create_mapping_side_effect,
            ),
            patch("ada_backend.services.git_sync_service.git_sync_repository.update_prompt_mapping_sync"),
        ):
            await sync_prompts_from_github(
                session=session,
                organization_id=org_id,
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                installation_id=42,
                commit_sha="abc12345",
                prompt_paths=["existing.md", "ok.md", "dup.md"],
            )

        session.rollback.assert_not_called()
        session.commit.assert_called_once()
        assert session.begin_nested.call_count == 2
