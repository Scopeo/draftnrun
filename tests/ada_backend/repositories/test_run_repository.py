from ada_backend.database import models as db
from ada_backend.repositories.run_repository import create_run


class _FakeRun:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeSession:
    def add(self, _obj):
        return None

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def test_run_retry_group_id_column_has_no_orm_default():
    assert db.Run.__table__.c.retry_group_id.default is None


def test_create_run_defaults_retry_group_id_to_distinct_group(monkeypatch):
    monkeypatch.setattr("ada_backend.repositories.run_repository.db.Run", _FakeRun)
    session = _FakeSession()

    run_without_retry_group = create_run(session=session, project_id="project-id")
    run_with_retry_group = create_run(session=session, project_id="project-id", retry_group_id="retry-group-id")

    assert run_without_retry_group.kwargs["retry_group_id"] != run_without_retry_group.kwargs["id"]
    assert run_with_retry_group.kwargs["retry_group_id"] == "retry-group-id"
