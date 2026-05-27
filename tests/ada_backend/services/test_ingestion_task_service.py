from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue, SourceAttributes
from ada_backend.services.ingestion_task_service import create_ingestion_task_by_organization

MODULE = "ada_backend.services.ingestion_task_service"


def _make_queue(source_id=None) -> IngestionTaskQueue:
    return IngestionTaskQueue(
        source_id=source_id,
        source_name="Test Source",
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=SourceAttributes(list_of_files_from_local_folder=[]),
    )


class TestCreateIngestionTaskSourceId:
    """Regression: every subprocess attempt for a task must see the same source_id.

    Previously the service passed `source_id=None` to both the DB row and Redis;
    each subprocess attempt then independently generated a fresh `uuid.uuid4()`,
    scattering chunks across orphan sources. The service must now assign a
    deterministic source_id at task creation.
    """

    def test_generates_source_id_when_payload_omits_it(self):
        organization_id = uuid4()
        task_id = uuid4()
        queue = _make_queue(source_id=None)

        with (
            patch(f"{MODULE}.create_ingestion_task", return_value=task_id) as mock_create,
            patch(f"{MODULE}.push_ingestion_task", return_value=True) as mock_push,
            patch(f"{MODULE}.track_ingestion_task_created"),
        ):
            create_ingestion_task_by_organization(
                session=MagicMock(),
                organization_id=organization_id,
                ingestion_task_data=queue,
            )

        repo_source_id = mock_create.call_args.args[5]
        assert isinstance(repo_source_id, UUID)

        pushed_source_id = mock_push.call_args.kwargs["source_id"]
        assert pushed_source_id == str(repo_source_id)

    def test_db_row_and_redis_payload_use_the_same_source_id(self):
        organization_id = uuid4()
        queue = _make_queue(source_id=None)

        with (
            patch(f"{MODULE}.create_ingestion_task", return_value=uuid4()) as mock_create,
            patch(f"{MODULE}.push_ingestion_task", return_value=True) as mock_push,
            patch(f"{MODULE}.track_ingestion_task_created"),
        ):
            create_ingestion_task_by_organization(
                session=MagicMock(),
                organization_id=organization_id,
                ingestion_task_data=queue,
            )

        repo_source_id = mock_create.call_args.args[5]
        pushed_source_id_str = mock_push.call_args.kwargs["source_id"]
        assert pushed_source_id_str is not None
        assert str(repo_source_id) == pushed_source_id_str

    def test_preserves_caller_provided_source_id_for_add_files_flow(self):
        organization_id = uuid4()
        existing_source_id = uuid4()
        queue = _make_queue(source_id=existing_source_id)

        with (
            patch(f"{MODULE}.create_ingestion_task", return_value=uuid4()) as mock_create,
            patch(f"{MODULE}.push_ingestion_task", return_value=True) as mock_push,
            patch(f"{MODULE}.track_ingestion_task_created"),
        ):
            create_ingestion_task_by_organization(
                session=MagicMock(),
                organization_id=organization_id,
                ingestion_task_data=queue,
            )

        assert mock_create.call_args.args[5] == existing_source_id
        assert mock_push.call_args.kwargs["source_id"] == str(existing_source_id)

    def test_two_independent_calls_produce_different_source_ids(self):
        organization_id = uuid4()

        captured_ids: list[UUID] = []

        def capture(*args, **kwargs):
            captured_ids.append(args[5])
            return uuid4()

        with (
            patch(f"{MODULE}.create_ingestion_task", side_effect=capture),
            patch(f"{MODULE}.push_ingestion_task", return_value=True),
            patch(f"{MODULE}.track_ingestion_task_created"),
        ):
            create_ingestion_task_by_organization(
                session=MagicMock(),
                organization_id=organization_id,
                ingestion_task_data=_make_queue(source_id=None),
            )
            create_ingestion_task_by_organization(
                session=MagicMock(),
                organization_id=organization_id,
                ingestion_task_data=_make_queue(source_id=None),
            )

        assert len(captured_ids) == 2
        assert captured_ids[0] != captured_ids[1]

    def test_failed_redis_push_marks_task_failed_with_assigned_source_id(self):
        organization_id = uuid4()
        task_id = uuid4()
        queue = _make_queue(source_id=None)

        with (
            patch(f"{MODULE}.create_ingestion_task", return_value=task_id) as mock_create,
            patch(f"{MODULE}.push_ingestion_task", return_value=False),
            patch(f"{MODULE}.track_ingestion_task_created"),
            patch(
                "ada_backend.repositories.ingestion_task_repository.update_ingestion_task",
            ) as mock_update,
        ):
            create_ingestion_task_by_organization(
                session=MagicMock(),
                organization_id=organization_id,
                ingestion_task_data=queue,
            )

        assigned_source_id = mock_create.call_args.args[5]
        update_source_id_arg = mock_update.call_args.args[2]
        assert update_source_id_arg == assigned_source_id


class TestCreateIngestionTaskErrors:
    def test_repo_failure_is_wrapped_in_value_error(self):
        with (
            patch(f"{MODULE}.create_ingestion_task", side_effect=RuntimeError("db down")),
            patch(f"{MODULE}.push_ingestion_task"),
            patch(f"{MODULE}.track_ingestion_task_created"),
        ):
            with pytest.raises(ValueError, match="Failed to create task"):
                create_ingestion_task_by_organization(
                    session=MagicMock(),
                    organization_id=uuid4(),
                    ingestion_task_data=_make_queue(source_id=None),
                )
