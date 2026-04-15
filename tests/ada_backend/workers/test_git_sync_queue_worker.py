from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.workers.git_sync_queue_worker import GitSyncQueueWorker


class TestRecoverOrphanedItem:
    @pytest.fixture
    def worker(self):
        with patch("ada_backend.workers.git_sync_queue_worker.settings"):
            return GitSyncQueueWorker()

    def test_updates_status_to_pending_retry(self, worker):
        config_id = uuid4()
        commit_sha = "abc123def456"
        config = SimpleNamespace(id=config_id)

        with patch("ada_backend.workers.git_sync_queue_worker.get_db_session") as mock_ctx:
            session = MagicMock()
            mock_ctx.return_value.__enter__ = MagicMock(return_value=session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("ada_backend.workers.git_sync_queue_worker.git_sync_repository") as repo_mock:
                repo_mock.get_git_sync_config_by_id.return_value = config
                worker.recover_orphaned_item({"config_id": str(config_id), "commit_sha": commit_sha})

            repo_mock.get_git_sync_config_by_id.assert_called_once_with(session, config_id)
            repo_mock.update_sync_status.assert_called_once_with(
                session, config_id=config_id, status="pending_retry", commit_sha=commit_sha
            )

    def test_skips_when_config_deleted(self, worker):
        config_id = uuid4()

        with patch("ada_backend.workers.git_sync_queue_worker.get_db_session") as mock_ctx:
            session = MagicMock()
            mock_ctx.return_value.__enter__ = MagicMock(return_value=session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("ada_backend.workers.git_sync_queue_worker.git_sync_repository") as repo_mock:
                repo_mock.get_git_sync_config_by_id.return_value = None
                worker.recover_orphaned_item({"config_id": str(config_id), "commit_sha": "abc123"})

            repo_mock.update_sync_status.assert_not_called()

    def test_handles_missing_commit_sha(self, worker):
        config_id = uuid4()
        config = SimpleNamespace(id=config_id)

        with patch("ada_backend.workers.git_sync_queue_worker.get_db_session") as mock_ctx:
            session = MagicMock()
            mock_ctx.return_value.__enter__ = MagicMock(return_value=session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("ada_backend.workers.git_sync_queue_worker.git_sync_repository") as repo_mock:
                repo_mock.get_git_sync_config_by_id.return_value = config
                worker.recover_orphaned_item({"config_id": str(config_id)})

            repo_mock.update_sync_status.assert_called_once_with(
                session, config_id=config_id, status="pending_retry", commit_sha=None
            )
