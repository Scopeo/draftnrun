import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import RunStatus
from ada_backend.services.webhooks.errors import WebhookServiceError
from ada_backend.services.webhooks.webhook_service import process_direct_trigger_event


def test_process_direct_trigger_event_persists_input_before_redis_handoff():
    session = MagicMock()
    project_id = uuid4()
    run_id = uuid4()
    retry_group_id = uuid4()
    event_id = "evt-123"
    env = "production"
    payload = {"messages": [{"role": "user", "content": "hello"}]}

    created_run = SimpleNamespace(id=run_id, retry_group_id=retry_group_id)
    with (
        patch("ada_backend.services.webhooks.webhook_service.check_and_set_webhook_event", return_value=True),
        patch("ada_backend.services.webhooks.webhook_service.create_run", return_value=created_run),
        patch("ada_backend.services.webhooks.webhook_service.save_run_input") as save_input_mock,
        patch("ada_backend.services.webhooks.webhook_service.push_webhook_event", return_value=True),
    ):
        result = asyncio.run(
            process_direct_trigger_event(
                session=session,
                project_id=project_id,
                env=env,
                payload=payload,
                event_id=event_id,
            )
        )

    assert result.status.value == "received"
    assert result.event_id == event_id
    save_input_mock.assert_called_once_with(
        session=session,
        retry_group_id=retry_group_id,
        project_id=project_id,
        input_data={**payload, "env": env},
    )


def test_process_direct_trigger_event_marks_run_failed_when_queue_fails():
    session = MagicMock()
    project_id = uuid4()
    run_id = uuid4()
    retry_group_id = uuid4()
    event_id = "evt-456"
    env = "production"
    payload = {"messages": []}

    created_run = SimpleNamespace(id=run_id, retry_group_id=retry_group_id)
    with (
        patch("ada_backend.services.webhooks.webhook_service.check_and_set_webhook_event", return_value=True),
        patch("ada_backend.services.webhooks.webhook_service.create_run", return_value=created_run),
        patch("ada_backend.services.webhooks.webhook_service.save_run_input"),
        patch("ada_backend.services.webhooks.webhook_service.push_webhook_event", return_value=False),
        patch("ada_backend.services.webhooks.webhook_service.run_repository.update_run_status") as update_status_mock,
    ):
        with pytest.raises(WebhookServiceError):
            asyncio.run(
                process_direct_trigger_event(
                    session=session,
                    project_id=project_id,
                    env=env,
                    payload=payload,
                    event_id=event_id,
                )
            )

    update_status_mock.assert_called_once()
    call_kwargs = update_status_mock.call_args.kwargs
    assert call_kwargs["run_id"] == run_id
    assert call_kwargs["status"] == RunStatus.FAILED
    assert call_kwargs["error"]["type"] == "QueueFailure"
    assert isinstance(call_kwargs["finished_at"], datetime)
    assert call_kwargs["finished_at"].tzinfo == timezone.utc
