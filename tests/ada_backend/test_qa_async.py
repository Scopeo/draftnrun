from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import RunStatus
from ada_backend.schemas.input_groundtruth_schema import QARunRequest
from ada_backend.services.qa.quality_assurance_service import run_qa_background


@pytest.mark.asyncio
async def test_run_qa_background_publishes_events_and_completes():
    session_id = uuid4()
    project_id = uuid4()
    dataset_id = uuid4()
    input_id_1 = uuid4()
    input_id_2 = uuid4()

    entry_1 = MagicMock(id=input_id_1, dataset_id=dataset_id, input={"msg": "a"}, groundtruth="ga")
    entry_2 = MagicMock(id=input_id_2, dataset_id=dataset_id, input={"msg": "b"}, groundtruth="gb")

    graph_runner_id = uuid4()
    run_request = QARunRequest(graph_runner_id=graph_runner_id, input_ids=[input_id_1, input_id_2])

    mock_chat_response = MagicMock(message="output_text", error=None)

    with (
        patch(
            "ada_backend.services.qa.quality_assurance_service.get_db_session"
        ) as mock_get_db_session,
        patch(
            "ada_backend.services.qa.quality_assurance_service.resolve_qa_entries_and_environment",
            return_value=([entry_1, entry_2], "draft"),
        ),
        patch(
            "ada_backend.services.qa.quality_assurance_service.update_qa_session_status"
        ) as mock_update_status,
        patch(
            "ada_backend.services.qa.quality_assurance_service.run_agent",
            new_callable=AsyncMock,
            return_value=mock_chat_response,
        ),
        patch(
            "ada_backend.services.qa.quality_assurance_service.upsert_version_output"
        ),
        patch(
            "ada_backend.services.qa.quality_assurance_service.publish_qa_event"
        ) as mock_publish,
    ):
        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_get_db_session.return_value = mock_ctx

        await run_qa_background(session_id, project_id, dataset_id, run_request)

    status_calls = mock_update_status.call_args_list
    assert any(c.kwargs.get("status") == RunStatus.RUNNING for c in status_calls)
    assert any(c.kwargs.get("status") == RunStatus.COMPLETED for c in status_calls)

    completed_call = next(c for c in status_calls if c.kwargs.get("status") == RunStatus.COMPLETED)
    assert completed_call.kwargs["total"] == 2
    assert completed_call.kwargs["passed"] == 2
    assert completed_call.kwargs["failed"] == 0

    published_types = [c[0][1]["type"] for c in mock_publish.call_args_list]
    assert published_types.count("qa.entry.started") == 2
    assert published_types.count("qa.entry.completed") == 2
    assert published_types.count("qa.completed") == 1

    completed_event = next(
        c[0][1] for c in mock_publish.call_args_list if c[0][1]["type"] == "qa.completed"
    )
    assert completed_event["summary"]["total"] == 2
    assert completed_event["summary"]["passed"] == 2

    for call in mock_publish.call_args_list:
        assert call[0][0] == session_id


@pytest.mark.asyncio
async def test_run_qa_background_handles_agent_failure():
    session_id = uuid4()
    project_id = uuid4()
    dataset_id = uuid4()
    input_id = uuid4()
    graph_runner_id = uuid4()

    entry = MagicMock(id=input_id, dataset_id=dataset_id, input={"msg": "a"}, groundtruth="g")
    run_request = QARunRequest(graph_runner_id=graph_runner_id, input_ids=[input_id])

    with (
        patch(
            "ada_backend.services.qa.quality_assurance_service.get_db_session"
        ) as mock_get_db_session,
        patch(
            "ada_backend.services.qa.quality_assurance_service.resolve_qa_entries_and_environment",
            return_value=([entry], "draft"),
        ),
        patch(
            "ada_backend.services.qa.quality_assurance_service.update_qa_session_status"
        ) as mock_update_status,
        patch(
            "ada_backend.services.qa.quality_assurance_service.run_agent",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM timeout"),
        ),
        patch(
            "ada_backend.services.qa.quality_assurance_service.upsert_version_output"
        ),
        patch(
            "ada_backend.services.qa.quality_assurance_service.publish_qa_event"
        ) as mock_publish,
    ):
        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_get_db_session.return_value = mock_ctx

        await run_qa_background(session_id, project_id, dataset_id, run_request)

    completed_call = next(
        c for c in mock_update_status.call_args_list if c.kwargs.get("status") == RunStatus.COMPLETED
    )
    assert completed_call.kwargs["failed"] == 1
    assert completed_call.kwargs["passed"] == 0

    completed_event = next(
        c[0][1] for c in mock_publish.call_args_list if c[0][1]["type"] == "qa.completed"
    )
    assert completed_event["summary"]["failed"] == 1
    assert completed_event["summary"]["passed"] == 0

    entry_completed = next(
        c[0][1] for c in mock_publish.call_args_list if c[0][1]["type"] == "qa.entry.completed"
    )
    assert entry_completed["success"] is False
    assert "LLM timeout" in entry_completed["error"]


@pytest.mark.asyncio
async def test_run_qa_background_publishes_qa_failed_on_global_error():
    session_id = uuid4()
    project_id = uuid4()
    dataset_id = uuid4()
    graph_runner_id = uuid4()

    run_request = QARunRequest(graph_runner_id=graph_runner_id, run_all=True)

    with (
        patch(
            "ada_backend.services.qa.quality_assurance_service.get_db_session"
        ) as mock_get_db_session,
        patch(
            "ada_backend.services.qa.quality_assurance_service.resolve_qa_entries_and_environment",
            side_effect=ValueError("No entries found"),
        ),
        patch(
            "ada_backend.services.qa.quality_assurance_service.update_qa_session_status"
        ) as mock_update_status,
        patch(
            "ada_backend.services.qa.quality_assurance_service.publish_qa_event"
        ) as mock_publish,
    ):
        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_get_db_session.return_value = mock_ctx

        await run_qa_background(session_id, project_id, dataset_id, run_request)

    status_calls = mock_update_status.call_args_list
    assert any(c.kwargs.get("status") == RunStatus.FAILED for c in status_calls)

    failed_call = next(c for c in status_calls if c.kwargs.get("status") == RunStatus.FAILED)
    assert "No entries found" in failed_call.kwargs["error"]["message"]

    failed_event = next(
        c[0][1] for c in mock_publish.call_args_list if c[0][1]["type"] == "qa.failed"
    )
    assert "No entries found" in failed_event["error"]["message"]
    assert mock_publish.call_args_list[0][0][0] == session_id
