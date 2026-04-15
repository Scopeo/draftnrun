import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from ada_backend.database.models import ProjectType
from ada_backend.routers.git_sync_router import _verify_github_signature
from ada_backend.services.git_sync_service import (
    GitSyncConfigNotFound,
    GitSyncError,
    GraphJsonNotFound,
    disconnect_sync,
    handle_github_push,
    import_from_github,
    sync_graph_from_github,
)
from ada_backend.utils.redis_client import push_git_sync_task


class TestVerifyGithubSignature:
    def test_valid_signature(self):
        secret = "test-secret"
        body = b'{"ref": "refs/heads/main"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_github_signature(body, sig, secret) is True

    def test_invalid_signature(self):
        secret = "test-secret"
        body = b'{"ref": "refs/heads/main"}'
        assert _verify_github_signature(body, "sha256=invalid", secret) is False

    def test_empty_signature(self):
        assert _verify_github_signature(b"body", "", "secret") is False

    def test_tampered_body(self):
        secret = "test-secret"
        original = b'{"ref": "refs/heads/main"}'
        sig = "sha256=" + hmac.new(secret.encode(), original, hashlib.sha256).hexdigest()
        tampered = b'{"ref": "refs/heads/evil"}'
        assert _verify_github_signature(tampered, sig, secret) is False


class TestSyncGraphFromGithub:
    @pytest.fixture
    def config(self):
        return SimpleNamespace(
            id=uuid4(),
            organization_id=uuid4(),
            project_id=uuid4(),
            github_owner="owner",
            github_repo_name="repo",
            github_repo="owner/repo",
            graph_folder="my-project",
            github_installation_id=12345,
            created_by_user_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_successful_sync(self, config):
        graph_json = json.dumps({
            "component_instances": [],
            "relationships": [],
            "edges": [],
            "port_mappings": [],
        })
        prev_prod = MagicMock(id=uuid4())

        session = MagicMock()
        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value=graph_json,
            ) as fetch_mock,
            patch(
                "ada_backend.services.git_sync_service.insert_graph_runner_and_bind_to_project",
            ) as insert_mock,
            patch(
                "ada_backend.services.git_sync_service.update_graph_service",
                new_callable=AsyncMock,
            ) as update_mock,
            patch(
                "ada_backend.services.git_sync_service.get_graph_runner_for_env",
                return_value=prev_prod,
            ) as get_prod_mock,
            patch("ada_backend.services.git_sync_service.update_graph_runner_env") as env_mock,
            patch("ada_backend.services.git_sync_service.compute_next_tag_version", return_value="v2") as tag_mock,
            patch("ada_backend.services.git_sync_service.update_graph_runner_tag_fields") as tag_fields_mock,
            patch("ada_backend.services.git_sync_service.track_deployed_to_production") as track_mock,
            patch("ada_backend.services.git_sync_service.git_sync_repository") as repo_mock,
        ):
            await sync_graph_from_github(session, config, "abc123def456")

        fetch_mock.assert_called_once_with(
            repo="owner/repo",
            path="my-project/graph.json",
            ref="abc123def456",
            installation_id=12345,
        )
        insert_mock.assert_called_once()
        update_mock.assert_called_once()
        assert update_mock.call_args.kwargs["bypass_validation"] is True
        get_prod_mock.assert_called_once()
        env_mock.assert_any_call(session, prev_prod.id, env=None, commit=False)
        tag_mock.assert_called_once_with(session, config.project_id)
        tag_fields_mock.assert_called_once()
        track_mock.assert_called_once_with(config.created_by_user_id, config.organization_id, config.project_id)
        repo_mock.update_sync_status.assert_called_once_with(
            session=session, config_id=config.id, status="success", commit_sha="abc123def456"
        )

    @pytest.mark.asyncio
    async def test_fetch_failure_records_status(self, config):
        session = MagicMock()
        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                side_effect=Exception("404 Not Found"),
            ),
            patch("ada_backend.services.git_sync_service.git_sync_repository") as repo_mock,
        ):
            with pytest.raises(GitSyncError, match="Failed to fetch graph from GitHub"):
                await sync_graph_from_github(session, config, "deadbeef")

        repo_mock.update_sync_status.assert_called_once_with(
            session=session, config_id=config.id, status="fetch_failed", commit_sha="deadbeef",
            error_message="404 Not Found",
        )

    @pytest.mark.asyncio
    async def test_invalid_json_records_status(self, config):
        session = MagicMock()
        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value="not valid json{{{",
            ),
            patch("ada_backend.services.git_sync_service.git_sync_repository") as repo_mock,
        ):
            with pytest.raises(GitSyncError, match="Invalid graph JSON"):
                await sync_graph_from_github(session, config, "badjson1")

        call_kwargs = repo_mock.update_sync_status.call_args.kwargs
        assert call_kwargs["session"] is session
        assert call_kwargs["config_id"] == config.id
        assert call_kwargs["status"] == "parse_failed"
        assert call_kwargs["commit_sha"] == "badjson1"
        assert call_kwargs["error_message"] is not None

    @pytest.mark.asyncio
    async def test_update_failure_records_error_message(self, config):
        graph_json = json.dumps({
            "component_instances": [],
            "relationships": [],
            "edges": [],
        })
        session = MagicMock()
        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value=graph_json,
            ),
            patch("ada_backend.services.git_sync_service.insert_graph_runner_and_bind_to_project"),
            patch(
                "ada_backend.services.git_sync_service.update_graph_service",
                new_callable=AsyncMock,
                side_effect=Exception("Parameter 'initial_prompt' not found"),
            ),
            patch("ada_backend.services.git_sync_service.git_sync_repository") as repo_mock,
        ):
            with pytest.raises(GitSyncError, match="Graph update failed"):
                await sync_graph_from_github(session, config, "badgraph1")

        repo_mock.update_sync_status.assert_called_once_with(
            session=session, config_id=config.id, status="update_failed", commit_sha="badgraph1",
            error_message="Parameter 'initial_prompt' not found",
        )

    @pytest.mark.asyncio
    async def test_deploy_failure_records_error_message(self, config):
        graph_json = json.dumps({
            "component_instances": [],
            "relationships": [],
            "edges": [],
        })
        session = MagicMock()
        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value=graph_json,
            ),
            patch("ada_backend.services.git_sync_service.insert_graph_runner_and_bind_to_project"),
            patch(
                "ada_backend.services.git_sync_service.update_graph_service",
                new_callable=AsyncMock,
            ),
            patch(
                "ada_backend.services.git_sync_service.get_graph_runner_for_env",
                side_effect=Exception("DB connection lost"),
            ),
            patch("ada_backend.services.git_sync_service.git_sync_repository") as repo_mock,
        ):
            with pytest.raises(GitSyncError, match="Graph deploy failed"):
                await sync_graph_from_github(session, config, "deployfail1")

        repo_mock.update_sync_status.assert_called_once_with(
            session=session, config_id=config.id, status="deploy_failed", commit_sha="deployfail1",
            error_message="DB connection lost",
        )

    @pytest.mark.asyncio
    async def test_success_clears_error_message(self, config):
        graph_json = json.dumps({
            "component_instances": [],
            "relationships": [],
            "edges": [],
        })
        prev_prod = MagicMock(id=uuid4())
        session = MagicMock()
        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.fetch_file",
                new_callable=AsyncMock,
                return_value=graph_json,
            ),
            patch("ada_backend.services.git_sync_service.insert_graph_runner_and_bind_to_project"),
            patch("ada_backend.services.git_sync_service.update_graph_service", new_callable=AsyncMock),
            patch("ada_backend.services.git_sync_service.get_graph_runner_for_env", return_value=prev_prod),
            patch("ada_backend.services.git_sync_service.update_graph_runner_env"),
            patch("ada_backend.services.git_sync_service.compute_next_tag_version", return_value="v1"),
            patch("ada_backend.services.git_sync_service.update_graph_runner_tag_fields"),
            patch("ada_backend.services.git_sync_service.track_deployed_to_production"),
            patch("ada_backend.services.git_sync_service.git_sync_repository") as repo_mock,
        ):
            await sync_graph_from_github(session, config, "goodcommit")

        repo_mock.update_sync_status.assert_called_once_with(
            session=session, config_id=config.id, status="success", commit_sha="goodcommit"
        )


class TestImportFromGithub:
    def _make_config(self, org_id, project_id, folder, **kwargs):
        return SimpleNamespace(
            id=uuid4(),
            organization_id=org_id,
            project_id=project_id,
            github_owner="owner",
            github_repo_name="repo",
            github_repo="owner/repo",
            graph_folder=folder,
            branch="main",
            github_installation_id=42,
            created_by_user_id=uuid4(),
            last_sync_at=None,
            last_sync_status=None,
            last_sync_commit_sha=None,
            created_at="2024-01-01",
            updated_at="2024-01-01",
            **kwargs,
        )

    @pytest.mark.asyncio
    async def test_imports_single_folder(self):
        session = MagicMock()
        org_id = uuid4()
        user_id = uuid4()
        project_id = uuid4()
        config_id = uuid4()

        project = SimpleNamespace(id=project_id, name="my-agent", organization_id=org_id)
        config = self._make_config(org_id, project_id, "my-agent")
        config.id = config_id

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.find_graph_json_folders",
                new_callable=AsyncMock,
                return_value=["my-agent"],
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_project_with_graph_runner",
                return_value=(project, uuid4()),
            ) as create_proj_mock,
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_git_sync_config",
                return_value=config,
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                return_value=True,
            ),
        ):
            imported, skipped = await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=user_id,
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
            )

        assert len(imported) == 1
        assert imported[0].graph_folder == "my-agent"
        assert imported[0].project_name == "my-agent"
        assert imported[0].status == "created"
        assert len(skipped) == 0
        create_proj_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_imports_with_agent_project_type(self):
        session = MagicMock()
        org_id = uuid4()
        project_id = uuid4()
        config_id = uuid4()

        project = SimpleNamespace(id=project_id, name="my-agent", organization_id=org_id)
        config = self._make_config(org_id, project_id, "my-agent")
        config.id = config_id

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.find_graph_json_folders",
                new_callable=AsyncMock,
                return_value=["my-agent"],
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_project_with_graph_runner",
                return_value=(project, uuid4()),
            ) as create_proj_mock,
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_git_sync_config",
                return_value=config,
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                return_value=True,
            ),
        ):
            await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=uuid4(),
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
                project_type=ProjectType.AGENT,
            )

        _, kwargs = create_proj_mock.call_args
        assert kwargs["project_type"] == ProjectType.AGENT

    @pytest.mark.asyncio
    async def test_imports_multiple_folders(self):
        session = MagicMock()
        org_id = uuid4()

        configs = {
            "agent-a": self._make_config(org_id, uuid4(), "agent-a"),
            "agent-b": self._make_config(org_id, uuid4(), "agent-b"),
        }

        def fake_create(
            session,
            organization_id,
            project_id,
            project_name,
            description,
            project_type,
            template,
            graph_id,
            add_input,
        ):
            return SimpleNamespace(id=project_id, name=project_name, organization_id=org_id), uuid4()

        def fake_create_config(**kwargs):
            return configs[kwargs["graph_folder"]]

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.find_graph_json_folders",
                new_callable=AsyncMock,
                return_value=["agent-a", "agent-b"],
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_project_with_graph_runner",
                side_effect=fake_create,
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_git_sync_config",
                side_effect=fake_create_config,
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                return_value=True,
            ),
        ):
            imported, skipped = await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=uuid4(),
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
            )

        assert len(imported) == 2
        assert {i.graph_folder for i in imported} == {"agent-a", "agent-b"}
        assert len(skipped) == 0

    @pytest.mark.asyncio
    async def test_skips_already_linked_folders(self):
        session = MagicMock()
        org_id = uuid4()

        existing_config = self._make_config(org_id, uuid4(), "agent-a")
        new_config = self._make_config(org_id, uuid4(), "agent-b")

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.find_graph_json_folders",
                new_callable=AsyncMock,
                return_value=["agent-a", "agent-b"],
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[existing_config],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_project_with_graph_runner",
                return_value=(SimpleNamespace(id=uuid4(), name="agent-b", organization_id=org_id), uuid4()),
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_git_sync_config",
                return_value=new_config,
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                return_value=True,
            ),
        ):
            imported, skipped = await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=uuid4(),
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
            )

        assert len(imported) == 1
        assert imported[0].graph_folder == "agent-b"
        assert skipped == ["agent-a"]

    @pytest.mark.asyncio
    async def test_no_graph_json_raises(self):
        session = MagicMock()

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.find_graph_json_folders",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            with pytest.raises(GraphJsonNotFound):
                await import_from_github(
                    session=session,
                    organization_id=uuid4(),
                    user_id=uuid4(),
                    github_owner="owner",
                    github_repo_name="repo",
                    branch="main",
                    github_installation_id=42,
                )

    @pytest.mark.asyncio
    async def test_root_level_graph_uses_repo_name(self):
        session = MagicMock()
        org_id = uuid4()
        pid = uuid4()
        project = SimpleNamespace(id=pid, name="repo", organization_id=org_id)
        config = self._make_config(org_id, pid, "")

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.find_graph_json_folders",
                new_callable=AsyncMock,
                return_value=[""],
            ),
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[],
            ),
            patch(
                "ada_backend.services.git_sync_service.create_project_with_graph_runner",
                return_value=(project, uuid4()),
            ) as create_mock,
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.create_git_sync_config",
                return_value=config,
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                return_value=True,
            ),
        ):
            imported, skipped = await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=uuid4(),
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
            )

        assert imported[0].project_name == "repo"
        assert create_mock.call_args.kwargs["project_name"] == "repo"

    @pytest.mark.asyncio
    async def test_integrity_error_skips_folder(self):
        session = MagicMock()
        org_id = uuid4()
        project = SimpleNamespace(id=uuid4(), name="my-agent", organization_id=org_id)

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.find_graph_json_folders",
                new_callable=AsyncMock,
                return_value=["my-agent"],
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
                side_effect=IntegrityError("INSERT", {}, Exception("unique constraint")),
            ),
        ):
            imported, skipped = await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=uuid4(),
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
            )

        assert len(imported) == 0
        assert skipped == ["my-agent"]
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueues_initial_sync_for_each_import(self):
        session = MagicMock()
        org_id = uuid4()
        config = self._make_config(org_id, uuid4(), "my-agent")
        project = SimpleNamespace(id=config.project_id, name="my-agent", organization_id=org_id)

        with (
            patch(
                "ada_backend.services.git_sync_service.github_client.get_branch_head_sha",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            patch(
                "ada_backend.services.git_sync_service.github_client.find_graph_json_folders",
                new_callable=AsyncMock,
                return_value=["my-agent"],
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
            ) as push_mock,
        ):
            await import_from_github(
                session=session,
                organization_id=org_id,
                user_id=uuid4(),
                github_owner="owner",
                github_repo_name="repo",
                branch="main",
                github_installation_id=42,
            )

        push_mock.assert_called_once_with(config.id, "abc123")


class TestHandleGithubPush:
    def test_passes_installation_id_to_repo(self):
        session = MagicMock()
        config = SimpleNamespace(
            id=uuid4(),
            graph_folder="my-agent",
        )
        with (
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[config],
            ) as repo_mock,
            patch("ada_backend.services.git_sync_service.push_git_sync_task", return_value=True),
        ):
            queued, failed = handle_github_push(
                session,
                "owner",
                "repo",
                "main",
                changed_files={"my-agent/graph.json"},
                commit_sha="abc123",
                github_installation_id=99,
            )

        repo_mock.assert_called_once_with(session, "owner", "repo", "main", github_installation_id=99)
        assert queued == 1
        assert failed == 0

    def test_works_without_installation_id(self):
        session = MagicMock()
        with patch(
            "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
            return_value=[],
        ) as repo_mock:
            queued, failed = handle_github_push(
                session,
                "owner",
                "repo",
                "main",
                changed_files=set(),
                commit_sha="abc123",
            )

        repo_mock.assert_called_once_with(session, "owner", "repo", "main", github_installation_id=None)
        assert queued == 0
        assert failed == 0

    def test_partial_enqueue_failure_retries_without_duplicates(self):
        session = MagicMock()
        config_a = SimpleNamespace(id=uuid4(), graph_folder="agent-a")
        config_b = SimpleNamespace(id=uuid4(), graph_folder="agent-b")

        push_results = {str(config_a.id): True, str(config_b.id): False}

        def fake_push(config_id, commit_sha):
            return push_results[str(config_id)]

        with (
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[config_a, config_b],
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                side_effect=fake_push,
            ) as push_mock,
        ):
            queued, failed = handle_github_push(
                session,
                "owner",
                "repo",
                "main",
                changed_files={"agent-a/graph.json", "agent-b/graph.json"},
                commit_sha="abc123",
            )

        assert queued == 1
        assert failed == 1
        assert push_mock.call_count == 2

        push_results[str(config_b.id)] = True
        with (
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_configs_by_repo_and_branch",
                return_value=[config_a, config_b],
            ),
            patch(
                "ada_backend.services.git_sync_service.push_git_sync_task",
                side_effect=fake_push,
            ) as push_mock,
        ):
            queued, failed = handle_github_push(
                session,
                "owner",
                "repo",
                "main",
                changed_files={"agent-a/graph.json", "agent-b/graph.json"},
                commit_sha="abc123",
            )

        assert queued == 2
        assert failed == 0


class TestPushGitSyncTaskDedup:
    def test_first_push_enqueues(self):
        client = MagicMock()
        client.set.return_value = True
        client.rpush.return_value = 1

        with patch("ada_backend.utils.redis_client.get_redis_client", return_value=client):
            result = push_git_sync_task(uuid4(), "abc123")

        assert result is True
        client.set.assert_called_once()
        client.rpush.assert_called_once()

    def test_duplicate_push_skips_enqueue(self):
        config_id = uuid4()
        client = MagicMock()
        client.set.return_value = None

        with patch("ada_backend.utils.redis_client.get_redis_client", return_value=client):
            result = push_git_sync_task(config_id, "abc123")

        assert result is True
        client.set.assert_called_once()
        client.rpush.assert_not_called()

    def test_rpush_failure_cleans_up_dedup_key(self):
        config_id = uuid4()
        client = MagicMock()
        client.set.return_value = True
        client.rpush.return_value = 0

        with patch("ada_backend.utils.redis_client.get_redis_client", return_value=client):
            result = push_git_sync_task(config_id, "abc123")

        assert result is False
        client.delete.assert_called_once()
        dedup_key = client.delete.call_args[0][0]
        assert str(config_id) in dedup_key
        assert "abc123" in dedup_key

    def test_redis_unavailable_returns_false(self):
        with patch("ada_backend.utils.redis_client.get_redis_client", return_value=None):
            result = push_git_sync_task(uuid4(), "abc123")

        assert result is False


class TestDisconnectSync:
    def test_raises_if_not_found(self):
        session = MagicMock()
        config_id = uuid4()

        with patch(
            "ada_backend.services.git_sync_service.git_sync_repository.get_git_sync_config_by_id",
            return_value=None,
        ):
            with pytest.raises(GitSyncConfigNotFound):
                disconnect_sync(session, config_id, uuid4())

    def test_raises_if_wrong_org(self):
        session = MagicMock()
        config_id = uuid4()
        org_id = uuid4()
        config = SimpleNamespace(id=config_id, organization_id=uuid4())

        with patch(
            "ada_backend.services.git_sync_service.git_sync_repository.get_git_sync_config_by_id",
            return_value=config,
        ):
            with pytest.raises(GitSyncConfigNotFound):
                disconnect_sync(session, config_id, org_id)

    def test_successful_disconnect(self):
        session = MagicMock()
        config_id = uuid4()
        org_id = uuid4()

        config = SimpleNamespace(
            id=config_id,
            organization_id=org_id,
            project_id=uuid4(),
        )

        with (
            patch(
                "ada_backend.services.git_sync_service.git_sync_repository.get_git_sync_config_by_id",
                return_value=config,
            ),
            patch("ada_backend.services.git_sync_service.git_sync_repository.delete_git_sync_config") as delete_mock,
        ):
            disconnect_sync(session, config_id, org_id)

        delete_mock.assert_called_once_with(session, config_id)
