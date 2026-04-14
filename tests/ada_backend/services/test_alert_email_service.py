from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from ada_backend.services.alert_email_service import create_alert_email_service

MODULE = "ada_backend.services.alert_email_service"


def _make_integrity_error(constraint_name: str) -> IntegrityError:
    orig = MagicMock()
    orig.diag.constraint_name = constraint_name
    return IntegrityError("INSERT ...", {}, orig)


class TestCreateAlertEmailService:
    @patch(f"{MODULE}.alert_email_repository")
    def test_returns_created_email(self, mock_repo):
        session = MagicMock()
        expected = MagicMock()
        mock_repo.create_alert_email.return_value = expected

        result = create_alert_email_service(session, uuid4(), "a@b.com")

        assert result is expected
        session.rollback.assert_not_called()

    @patch(f"{MODULE}.alert_email_repository")
    def test_returns_409_on_duplicate_email_constraint(self, mock_repo):
        session = MagicMock()
        mock_repo.create_alert_email.side_effect = _make_integrity_error("uq_project_alert_email")

        with pytest.raises(HTTPException) as exc_info:
            create_alert_email_service(session, uuid4(), "dup@test.com")

        assert exc_info.value.status_code == 409
        assert "dup@test.com" in exc_info.value.detail
        session.rollback.assert_called_once()

    @patch(f"{MODULE}.alert_email_repository")
    def test_reraises_unrelated_integrity_error(self, mock_repo):
        session = MagicMock()
        mock_repo.create_alert_email.side_effect = _make_integrity_error("some_other_constraint")

        with pytest.raises(IntegrityError):
            create_alert_email_service(session, uuid4(), "a@b.com")

        session.rollback.assert_called_once()

    @patch(f"{MODULE}.alert_email_repository")
    def test_reraises_integrity_error_without_diag(self, mock_repo):
        session = MagicMock()
        orig = Exception("raw db error")
        mock_repo.create_alert_email.side_effect = IntegrityError("INSERT ...", {}, orig)

        with pytest.raises(IntegrityError):
            create_alert_email_service(session, uuid4(), "a@b.com")

        session.rollback.assert_called_once()
