from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ada_backend.services.alert_email_service import create_alert_email_service
from ada_backend.services.errors import DuplicateAlertEmailError

MODULE = "ada_backend.services.alert_email_service"


class TestCreateAlertEmailService:
    @patch(f"{MODULE}.alert_email_repository")
    def test_returns_created_email(self, mock_repo):
        session = MagicMock()
        expected = MagicMock()
        mock_repo.create_alert_email.return_value = expected

        result = create_alert_email_service(session, uuid4(), "a@b.com")

        assert result is expected

    @patch(f"{MODULE}.alert_email_repository")
    def test_returns_409_on_duplicate_email(self, mock_repo):
        session = MagicMock()
        mock_repo.create_alert_email.side_effect = DuplicateAlertEmailError("dup@test.com")

        with pytest.raises(HTTPException) as exc_info:
            create_alert_email_service(session, uuid4(), "dup@test.com")

        assert exc_info.value.status_code == 409
        assert "dup@test.com" in exc_info.value.detail
