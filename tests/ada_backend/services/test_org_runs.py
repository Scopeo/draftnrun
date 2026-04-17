from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import CallType, RunStatus
from ada_backend.services.errors import RunNotFound
from ada_backend.services.run_service import get_org_run_input, get_org_runs

MODULE = "ada_backend.services.run_service"


class TestGetOrgRuns:
    def _make_session(self):
        return MagicMock()

    def test_returns_paginated_results(self):
        session = self._make_session()
        org_id = uuid4()
        run_id = uuid4()
        project_id = uuid4()

        fake_rows = [
            {
                "id": run_id,
                "project_id": project_id,
                "project_name": "My Agent",
                "status": RunStatus.COMPLETED,
                "trigger": CallType.API,
                "trace_id": "0xabc123",
                "error": None,
                "retry_group_id": uuid4(),
                "attempt_number": 1,
                "attempt_count": 1,
                "input_available": True,
                "started_at": datetime.now(timezone.utc),
                "finished_at": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
            }
        ]

        with patch(f"{MODULE}.run_repository") as repo:
            repo.count_runs_by_organization.return_value = 1
            repo.get_runs_by_organization.return_value = fake_rows

            items, total = get_org_runs(session, organization_id=org_id, page=1, page_size=50)

        assert total == 1
        assert len(items) == 1
        assert items[0].project_name == "My Agent"
        assert items[0].status == RunStatus.COMPLETED

        repo.count_runs_by_organization.assert_called_once_with(
            session,
            organization_id=org_id,
            statuses=None,
            project_ids=None,
            trigger=None,
            date_from=None,
            date_to=None,
        )
        repo.get_runs_by_organization.assert_called_once()

    def test_passes_filters_to_repository(self):
        session = self._make_session()
        org_id = uuid4()
        project_id = uuid4()

        with patch(f"{MODULE}.run_repository") as repo:
            repo.count_runs_by_organization.return_value = 0
            repo.get_runs_by_organization.return_value = []

            get_org_runs(
                session,
                organization_id=org_id,
                statuses=[RunStatus.FAILED],
                project_ids=[project_id],
                trigger=CallType.WEBHOOK,
            )

        call_kwargs = repo.count_runs_by_organization.call_args.kwargs
        assert call_kwargs["statuses"] == [RunStatus.FAILED]
        assert call_kwargs["project_ids"] == [project_id]
        assert call_kwargs["trigger"] == CallType.WEBHOOK

    def test_string_error_coerced_to_dict(self):
        session = self._make_session()
        org_id = uuid4()

        fake_rows = [
            {
                "id": uuid4(),
                "project_id": uuid4(),
                "project_name": "Agent",
                "status": RunStatus.FAILED,
                "trigger": CallType.API,
                "trace_id": None,
                "error": "Error running agent: Traceback ...",
                "retry_group_id": uuid4(),
                "attempt_number": 1,
                "attempt_count": 1,
                "input_available": False,
                "started_at": datetime.now(timezone.utc),
                "finished_at": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
            }
        ]

        with patch(f"{MODULE}.run_repository") as repo:
            repo.count_runs_by_organization.return_value = 1
            repo.get_runs_by_organization.return_value = fake_rows

            items, total = get_org_runs(session, organization_id=org_id)

        assert total == 1
        assert items[0].error == {"message": "Error running agent: Traceback ..."}

    def test_empty_results(self):
        session = self._make_session()
        org_id = uuid4()

        with patch(f"{MODULE}.run_repository") as repo:
            repo.count_runs_by_organization.return_value = 0
            repo.get_runs_by_organization.return_value = []

            items, total = get_org_runs(session, organization_id=org_id)

        assert total == 0
        assert items == []


class TestGetOrgRunInput:
    def _make_session(self):
        return MagicMock()

    def test_returns_input_data(self):
        session = self._make_session()
        org_id = uuid4()
        run_id = uuid4()
        project_id = uuid4()
        retry_group_id = uuid4()

        fake_run = MagicMock()
        fake_run.id = run_id
        fake_run.project_id = project_id
        fake_run.retry_group_id = retry_group_id

        fake_project = MagicMock()
        fake_project.organization_id = org_id

        input_data = {"messages": [{"role": "user", "content": "hello"}]}

        with (
            patch(f"{MODULE}.run_repository") as repo,
            patch(f"{MODULE}.get_project", return_value=fake_project),
            patch(f"{MODULE}.get_run_input", return_value=input_data),
        ):
            repo.get_run.return_value = fake_run

            result = get_org_run_input(session, run_id=run_id, organization_id=org_id)

        assert result == input_data

    def test_raises_run_not_found_when_missing(self):
        session = self._make_session()

        with patch(f"{MODULE}.run_repository") as repo:
            repo.get_run.return_value = None
            with pytest.raises(RunNotFound):
                get_org_run_input(session, run_id=uuid4(), organization_id=uuid4())

    def test_raises_run_not_found_when_wrong_org(self):
        session = self._make_session()
        run_id = uuid4()
        org_id = uuid4()
        wrong_org_id = uuid4()

        fake_run = MagicMock()
        fake_run.id = run_id
        fake_run.project_id = uuid4()
        fake_run.retry_group_id = uuid4()

        fake_project = MagicMock()
        fake_project.organization_id = wrong_org_id

        with (
            patch(f"{MODULE}.run_repository") as repo,
            patch(f"{MODULE}.get_project", return_value=fake_project),
        ):
            repo.get_run.return_value = fake_run
            with pytest.raises(RunNotFound):
                get_org_run_input(session, run_id=run_id, organization_id=org_id)

    def test_returns_none_when_no_input_persisted(self):
        session = self._make_session()
        org_id = uuid4()
        run_id = uuid4()
        project_id = uuid4()

        fake_run = MagicMock()
        fake_run.id = run_id
        fake_run.project_id = project_id
        fake_run.retry_group_id = uuid4()

        fake_project = MagicMock()
        fake_project.organization_id = org_id

        with (
            patch(f"{MODULE}.run_repository") as repo,
            patch(f"{MODULE}.get_project", return_value=fake_project),
            patch(f"{MODULE}.get_run_input", return_value=None),
        ):
            repo.get_run.return_value = fake_run

            result = get_org_run_input(session, run_id=run_id, organization_id=org_id)

        assert result is None

    def test_falls_back_to_run_id_when_no_retry_group(self):
        session = self._make_session()
        org_id = uuid4()
        run_id = uuid4()
        project_id = uuid4()

        fake_run = MagicMock()
        fake_run.id = run_id
        fake_run.project_id = project_id
        fake_run.retry_group_id = None

        fake_project = MagicMock()
        fake_project.organization_id = org_id

        with (
            patch(f"{MODULE}.run_repository") as repo,
            patch(f"{MODULE}.get_project", return_value=fake_project),
            patch(f"{MODULE}.get_run_input", return_value={"messages": []}) as get_input_mock,
        ):
            repo.get_run.return_value = fake_run

            get_org_run_input(session, run_id=run_id, organization_id=org_id)

        get_input_mock.assert_called_once_with(session, retry_group_id=run_id)
