"""HTTP contract tests for QA router error remaps after centralized handling.

``QADatasetNotInProjectError`` defaults to 400 (inherited from ``QAServiceError``)
to preserve the historical contract on update/delete/columns/import endpoints.
The two run endpoints remap it to 404 locally in the router; these tests lock
that remap in so a future refactor pass cannot silently drop it.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ada_backend.routers.quality_assurance_router import run_qa_async_endpoint, run_qa_endpoint
from ada_backend.schemas.input_groundtruth_schema import QARunRequest
from ada_backend.services.qa.qa_error import QADatasetNotInProjectError


def _fake_user():
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.mark.asyncio
async def test_run_qa_endpoint_remaps_qa_dataset_not_in_project_to_404():
    project_id, dataset_id = uuid4(), uuid4()
    run_request = QARunRequest(graph_runner_id=uuid4(), run_all=True)

    with patch(
        "ada_backend.routers.quality_assurance_router.run_qa_service",
        new_callable=AsyncMock,
        side_effect=QADatasetNotInProjectError(project_id, dataset_id),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await run_qa_endpoint(
                project_id=project_id,
                dataset_id=dataset_id,
                run_request=run_request,
                user=_fake_user(),
                session=MagicMock(),
            )
    assert exc_info.value.status_code == 404
    assert str(dataset_id) in exc_info.value.detail


@pytest.mark.asyncio
async def test_run_qa_async_endpoint_remaps_qa_dataset_not_in_project_to_404():
    project_id, dataset_id = uuid4(), uuid4()
    run_request = QARunRequest(graph_runner_id=uuid4(), run_all=True)

    with patch(
        "ada_backend.routers.quality_assurance_router.validate_qa_run_request",
        side_effect=QADatasetNotInProjectError(project_id, dataset_id),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await run_qa_async_endpoint(
                project_id=project_id,
                dataset_id=dataset_id,
                run_request=run_request,
                user=_fake_user(),
                session=MagicMock(),
            )
    assert exc_info.value.status_code == 404
    assert str(dataset_id) in exc_info.value.detail
