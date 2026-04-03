from unittest.mock import MagicMock
from uuid import uuid4

from ada_backend.repositories.run_input_repository import (
    get_run_input,
    save_run_input,
)


class TestSaveRunInput:
    def test_upsert_inserts_without_inline_cleanup(self):
        session = MagicMock()
        retry_group_id = uuid4()
        project_id = uuid4()
        input_data = {"text": "hello"}

        save_run_input(session, retry_group_id=retry_group_id, project_id=project_id, input_data=input_data)

        assert session.execute.call_count == 1
        session.commit.assert_called_once()

    def test_duplicate_retry_group_id_does_not_raise(self):
        session = MagicMock()
        retry_group_id = uuid4()
        project_id = uuid4()

        save_run_input(session, retry_group_id=retry_group_id, project_id=project_id, input_data={"a": 1})
        save_run_input(session, retry_group_id=retry_group_id, project_id=project_id, input_data={"a": 1})

        assert session.execute.call_count == 2
        assert session.commit.call_count == 2


class TestGetRunInput:
    def test_returns_input_data_when_found(self):
        session = MagicMock()
        retry_group_id = uuid4()
        mock_row = MagicMock()
        mock_row.input_data = {"text": "hello"}
        session.query.return_value.filter.return_value.first.return_value = mock_row

        result = get_run_input(session, retry_group_id=retry_group_id)

        assert result == {"text": "hello"}

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        retry_group_id = uuid4()
        session.query.return_value.filter.return_value.first.return_value = None

        result = get_run_input(session, retry_group_id=retry_group_id)

        assert result is None
