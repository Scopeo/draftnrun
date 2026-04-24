import logging
from datetime import datetime, timezone
from typing import Annotated, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ada_backend.database.models import DatasetProject, DatasetProjectAssociation, RunStatus
from ada_backend.database.setup_db import get_db
from ada_backend.repositories.qa_session_repository import update_qa_session_status
from ada_backend.repositories.quality_assurance_repository import (
    check_dataset_belongs_to_organization,
    check_dataset_belongs_to_project,
)
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
    user_has_access_to_project_dependency,
)
from ada_backend.routers.router_utils import resolve_organization_id
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.dataset_schema import (
    DatasetCreateList,
    DatasetDeleteList,
    DatasetListResponse,
    DatasetProjectAssociationRequest,
    DatasetResponse,
)
from ada_backend.schemas.input_groundtruth_schema import (
    InputGroundtruthCreateList,
    InputGroundtruthDeleteList,
    InputGroundtruthResponse,
    InputGroundtruthResponseList,
    InputGroundtruthUpdateList,
    PaginatedInputGroundtruthResponse,
    QARunRequest,
    QARunResponse,
    QASessionAcceptedSchema,
    QASessionResponseSchema,
)
from ada_backend.schemas.qa_metadata_schema import QAColumnResponse
from ada_backend.services.errors import (
    GraphNotBoundToProjectError,
    ProjectNotFound,
    QADatasetNotFound,
    QAInputValidationError,
    QASessionNotFound,
)
from ada_backend.services.qa.qa_error import (
    CSVEmptyFileError,
    CSVExportError,
    CSVInvalidJSONError,
    CSVInvalidPositionError,
    CSVMissingDatasetColumnError,
    CSVNonUniquePositionError,
    QAColumnNotFoundError,
    QADatasetNotInOrganizationError,
    QADatasetNotInProjectError,
    QADuplicatePositionError,
    QAPartialPositionError,
)
from ada_backend.services.qa.qa_metadata_service import (
    create_qa_column_project_service,
    create_qa_column_service,
    delete_qa_column_project_service,
    delete_qa_column_service,
    get_qa_columns_by_dataset_project_service,
    get_qa_columns_by_dataset_service,
    rename_qa_column_project_service,
    rename_qa_column_service,
)
from ada_backend.services.qa.quality_assurance_service import (
    create_datasets_service,
    create_inputs_groundtruths_service,
    create_qa_session_service,
    delete_datasets_service,
    delete_inputs_groundtruths_service,
    export_qa_data_to_csv_service,
    get_datasets_by_organization_service,
    get_datasets_by_project_service,
    get_inputs_groundtruths_with_version_outputs_service,
    get_outputs_by_graph_runner_service,
    get_qa_session_service,
    get_version_output_ids_by_input_ids_and_graph_runner_service,
    import_qa_data_from_csv_service,
    list_qa_sessions_service,
    run_qa_service,
    save_conversation_to_groundtruth_service,
    set_dataset_projects_service,
    update_dataset_service,
    update_inputs_groundtruths_service,
    validate_qa_run_request,
)
from ada_backend.utils.redis_client import push_qa_task

router = APIRouter(tags=["Quality Assurance"])
LOGGER = logging.getLogger(__name__)


def _validate_dataset_in_organization(session: Session, organization_id: UUID, dataset_id: UUID) -> None:
    if not check_dataset_belongs_to_organization(session, organization_id, dataset_id):
        raise QADatasetNotInOrganizationError(organization_id, dataset_id)


# ══════════════════════════════════════════════════════════════════════
# Organization-scoped endpoints
# ══════════════════════════════════════════════════════════════════════

# ── Organization-scoped dataset CRUD ─────────────────────────────────

@router.get(
    "/organizations/{organization_id}/qa/datasets",
    response_model=List[DatasetResponse],
    summary="Get Datasets by Organization",
    tags=["Quality Assurance"],
)
def get_datasets_by_organization_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[DatasetResponse]:
    return get_datasets_by_organization_service(session, organization_id)


@router.post(
    "/organizations/{organization_id}/qa/datasets",
    response_model=DatasetListResponse,
    summary="Create Datasets (Organization)",
    tags=["Quality Assurance"],
)
def create_dataset_by_organization_endpoint(
    organization_id: UUID,
    dataset_data: DatasetCreateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> DatasetListResponse:
    return create_datasets_service(session, organization_id, dataset_data)


@router.patch(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}",
    response_model=DatasetResponse,
    summary="Update Dataset (Organization)",
    tags=["Quality Assurance"],
)
def update_dataset_by_organization_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    dataset_name: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> DatasetResponse:
    return update_dataset_service(session, organization_id, dataset_id, dataset_name)


@router.delete(
    "/organizations/{organization_id}/qa/datasets",
    summary="Delete Datasets (Organization)",
    tags=["Quality Assurance"],
)
def delete_dataset_by_organization_endpoint(
    organization_id: UUID,
    delete_data: DatasetDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    deleted_count = delete_datasets_service(session, organization_id, delete_data)
    return {"message": f"Deleted {deleted_count} datasets successfully"}


@router.put(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/projects",
    response_model=DatasetResponse,
    summary="Set Dataset Project Associations",
    tags=["Quality Assurance"],
)
def set_dataset_projects_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    body: DatasetProjectAssociationRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> DatasetResponse:
    return set_dataset_projects_service(session, organization_id, dataset_id, body.project_ids)


# ── Organization-scoped QA Metadata (Custom Columns) ────────────────

@router.get(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/custom-columns",
    response_model=List[QAColumnResponse],
    summary="Get Custom Columns for Dataset (Organization)",
    tags=["Quality Assurance"],
)
def get_columns_by_dataset_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[QAColumnResponse]:
    try:
        return get_qa_columns_by_dataset_service(session, organization_id, dataset_id)
    except QADatasetNotInOrganizationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get columns for dataset {dataset_id} in org {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/custom-columns",
    response_model=QAColumnResponse,
    summary="Add Custom Column to Dataset (Organization)",
    tags=["Quality Assurance"],
)
def add_column_to_dataset_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    column_name: str = Body(..., embed=True),
) -> QAColumnResponse:
    try:
        return create_qa_column_service(session, organization_id, dataset_id, column_name)
    except QADatasetNotInOrganizationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to add column to dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/custom-columns/{column_id}",
    response_model=QAColumnResponse,
    summary="Rename Custom Column (Organization)",
    tags=["Quality Assurance"],
)
def rename_column_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    column_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    column_name: str = Body(..., embed=True),
) -> QAColumnResponse:
    try:
        return rename_qa_column_service(session, organization_id, dataset_id, column_id, column_name)
    except QADatasetNotInOrganizationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except QAColumnNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to rename column {column_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/custom-columns/{column_id}",
    summary="Delete Custom Column (Organization)",
    tags=["Quality Assurance"],
)
def delete_column_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    column_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    try:
        return delete_qa_column_service(session, organization_id, dataset_id, column_id)
    except QADatasetNotInOrganizationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except QAColumnNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to delete column {column_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# ── Organization-scoped entries, CSV import/export ───────────────────

@router.get(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
    response_model=PaginatedInputGroundtruthResponse,
    summary="Get Input-Groundtruth Entries by Dataset (Organization)",
    tags=["Quality Assurance"],
)
def get_inputs_groundtruths_by_dataset_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(100, ge=1, le=1000, description="Number of items per page"),
) -> PaginatedInputGroundtruthResponse:
    try:
        _validate_dataset_in_organization(session, organization_id, dataset_id)
        return get_inputs_groundtruths_with_version_outputs_service(session, dataset_id, page, page_size)
    except QADatasetNotInOrganizationError:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id} not found in organization {organization_id}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/outputs",
    response_model=Dict[UUID, str],
    summary="Get Outputs for a Graph Runner (Organization)",
    tags=["Quality Assurance"],
)
def get_outputs_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    graph_runner_id: UUID = Query(..., description="Graph runner ID to get outputs for"),
) -> Dict[UUID, str]:
    try:
        _validate_dataset_in_organization(session, organization_id, dataset_id)
        return get_outputs_by_graph_runner_service(session, dataset_id, graph_runner_id)
    except QADatasetNotInOrganizationError:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id} not found in organization {organization_id}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get outputs for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
    response_model=InputGroundtruthResponseList,
    summary="Create Input-Groundtruth Entries (Organization)",
    tags=["Quality Assurance"],
)
def create_input_groundtruth_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    input_groundtruth_data: InputGroundtruthCreateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> InputGroundtruthResponseList:
    try:
        _validate_dataset_in_organization(session, organization_id, dataset_id)
        return create_inputs_groundtruths_service(session, dataset_id, input_groundtruth_data)
    except QADatasetNotInOrganizationError:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id} not found in organization {organization_id}",
        )
    except (QADuplicatePositionError, QAPartialPositionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
    response_model=InputGroundtruthResponseList,
    summary="Update Input-Groundtruth Entries (Organization)",
    tags=["Quality Assurance"],
)
def update_input_groundtruth_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    input_groundtruth_data: InputGroundtruthUpdateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> InputGroundtruthResponseList:
    try:
        _validate_dataset_in_organization(session, organization_id, dataset_id)
        return update_inputs_groundtruths_service(session, dataset_id, input_groundtruth_data)
    except QADatasetNotInOrganizationError:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id} not found in organization {organization_id}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to update entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
    summary="Delete Input-Groundtruth Entries (Organization)",
    tags=["Quality Assurance"],
)
def delete_input_groundtruth_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    delete_data: InputGroundtruthDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    try:
        _validate_dataset_in_organization(session, organization_id, dataset_id)
        deleted_count = delete_inputs_groundtruths_service(session, dataset_id, delete_data)
        return {"message": f"Deleted {deleted_count} input-groundtruth entries successfully"}
    except QADatasetNotInOrganizationError:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id} not found in organization {organization_id}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries/from-history",
    response_model=List[InputGroundtruthResponse],
    summary="Create Entry from History (Organization)",
    tags=["Quality Assurance"],
)
async def create_entry_from_history_org(
    organization_id: UUID,
    dataset_id: UUID,
    trace_id: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[InputGroundtruthResponse]:
    try:
        _validate_dataset_in_organization(session, organization_id, dataset_id)
        return save_conversation_to_groundtruth_service(
            session=session,
            trace_id=trace_id,
            dataset_id=dataset_id,
        )
    except QADatasetNotInOrganizationError:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id} not found in organization {organization_id}",
        )
    except (QADuplicatePositionError, QAPartialPositionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to save trace {trace_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/export",
    summary="Export QA Data to CSV (Organization)",
    tags=["Quality Assurance"],
)
def export_qa_data_to_csv_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    graph_runner_id: UUID = Query(..., description="Graph runner ID to filter outputs"),
) -> Response:
    try:
        _validate_dataset_in_organization(session, organization_id, dataset_id)
        csv_content = export_qa_data_to_csv_service(session, dataset_id, graph_runner_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"qa_export_{dataset_id}_{timestamp}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except QADatasetNotInOrganizationError:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id} not found in organization {organization_id}",
        )
    except CSVExportError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/import",
    response_model=InputGroundtruthResponseList,
    summary="Import QA Data from CSV (Organization)",
    tags=["Quality Assurance"],
)
async def import_qa_data_from_csv_org_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    file: Annotated[UploadFile, File(..., description="CSV file to import")],
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> InputGroundtruthResponseList:
    try:
        _validate_dataset_in_organization(session, organization_id, dataset_id)
        await file.seek(0)
        return import_qa_data_from_csv_service(
            session=session,
            organization_id=organization_id,
            dataset_id=dataset_id,
            csv_file=file.file,
        )
    except QADatasetNotInOrganizationError:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id} not found in organization {organization_id}",
        )
    except (
        CSVEmptyFileError,
        CSVInvalidJSONError,
        CSVMissingDatasetColumnError,
        CSVNonUniquePositionError,
        CSVInvalidPositionError,
    ) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to import QA data for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# ══════════════════════════════════════════════════════════════════════
# Project-scoped QA runs and sessions (NOT deprecated)
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/projects/{project_id}/qa/version-outputs",
    summary="Get Version Output IDs by Input IDs and Graph Runner",
    tags=["Quality Assurance"],
)
def get_version_output_ids_endpoint(
    graph_runner_id: UUID,
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    input_ids: List[UUID] = Query(..., description="List of Input IDs"),
) -> Dict[UUID, Optional[UUID]]:
    return get_version_output_ids_by_input_ids_and_graph_runner_service(
        session=session, input_ids=input_ids, graph_runner_id=graph_runner_id, project_id=project_id
    )


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/run",
    response_model=QARunResponse,
    summary="Run QA Process on Dataset Inputs",
    tags=["Quality Assurance"],
)
async def run_qa_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    run_request: QARunRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> QARunResponse:
    try:
        return await run_qa_service(session, project_id, dataset_id, run_request)
    except QADatasetNotInProjectError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except GraphNotBoundToProjectError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/run/async",
    response_model=QASessionAcceptedSchema,
    status_code=202,
    summary="Run QA Process Async (WebSocket streaming)",
    tags=["Quality Assurance"],
)
async def run_qa_async_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    run_request: QARunRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> QASessionAcceptedSchema:
    try:
        validate_qa_run_request(session, project_id, dataset_id, run_request)
    except QADatasetNotInProjectError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    qa_session = create_qa_session_service(
        session,
        project_id=project_id,
        dataset_id=dataset_id,
        graph_runner_id=run_request.graph_runner_id,
    )
    if not push_qa_task(
        session_id=qa_session.id,
        project_id=project_id,
        dataset_id=dataset_id,
        run_request_data=run_request.model_dump(mode="json"),
    ):
        update_qa_session_status(
            session, qa_session.id,
            status=RunStatus.FAILED,
            error={"message": "Failed to enqueue QA run; Redis unavailable.", "type": "EnqueueError"},
        )
        raise HTTPException(
            status_code=503,
            detail="QA session created but could not be enqueued. Try again.",
        )
    return QASessionAcceptedSchema(session_id=qa_session.id)


@router.get(
    "/projects/{project_id}/qa/sessions",
    response_model=List[QASessionResponseSchema],
    summary="List QA Sessions",
    tags=["Quality Assurance"],
)
def list_qa_sessions_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    dataset_id: Optional[UUID] = Query(None, description="Filter by dataset"),
) -> List[QASessionResponseSchema]:
    return list_qa_sessions_service(session, project_id, dataset_id)


@router.get(
    "/projects/{project_id}/qa/sessions/{qa_session_id}",
    response_model=QASessionResponseSchema,
    summary="Get QA Session",
    tags=["Quality Assurance"],
)
def get_qa_session_endpoint(
    project_id: UUID,
    qa_session_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> QASessionResponseSchema:
    return get_qa_session_service(session, qa_session_id, project_id)


# ══════════════════════════════════════════════════════════════════════
# Deprecated project-scoped endpoints (use org-scoped equivalents)
# ══════════════════════════════════════════════════════════════════════

# ── Deprecated dataset CRUD ──────────────────────────────────────────

@router.get(
    "/projects/{project_id}/qa/datasets",
    deprecated=True,
    response_model=List[DatasetResponse],
    summary="Get Datasets by Project",
    tags=["Quality Assurance"],
)
def get_datasets_by_project_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[DatasetResponse]:
    """
    Get all datasets for a project.

    This endpoint allows users to retrieve all datasets associated with a specific project
    for quality assurance purposes.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    return get_datasets_by_project_service(session, project_id)


@router.post(
    "/projects/{project_id}/qa/datasets",
    deprecated=True,
    response_model=DatasetListResponse,
    summary="Create Datasets",
    tags=["Quality Assurance"],
)
def create_dataset_endpoint(
    project_id: UUID,
    dataset_data: DatasetCreateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> DatasetListResponse:
    """
    Create datasets for a project.

    This endpoint allows users to create multiple datasets for quality assurance purposes.
    All datasets will be associated with the specified project.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        organization_id = resolve_organization_id(session, project_id)
        response = create_datasets_service(session, organization_id, dataset_data)
        dataset_ids = [dataset_resp.id for dataset_resp in response.datasets]
        session.query(DatasetProject).filter(
            DatasetProject.id.in_(dataset_ids)
        ).update({"project_id": project_id}, synchronize_session=False)
        session.add_all(
            [DatasetProjectAssociation(dataset_id=did, project_id=project_id) for did in dataset_ids]
        )
        session.commit()
        for dataset_resp in response.datasets:
            dataset_resp.project_ids = [project_id]
        return response
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch(
    "/projects/{project_id}/qa/datasets/{dataset_id}",
    deprecated=True,
    response_model=DatasetResponse,
    summary="Update Dataset",
    tags=["Quality Assurance"],
)
def update_dataset_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    dataset_name: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> DatasetResponse:
    """
    Update dataset.

    This endpoint allows users to update a single dataset.
    Only the fields provided in the request will be updated.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        organization_id = resolve_organization_id(session, project_id)
        if not check_dataset_belongs_to_project(session, project_id, dataset_id):
            raise QADatasetNotInProjectError(project_id, dataset_id)
        return update_dataset_service(session, organization_id, dataset_id, dataset_name)
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except QADatasetNotInProjectError:
        raise HTTPException(
            status_code=403,
            detail=f"Dataset {dataset_id} is not associated with project {project_id}",
        )


@router.delete(
    "/projects/{project_id}/qa/datasets",
    deprecated=True,
    summary="Delete Datasets",
    tags=["Quality Assurance"],
)
def delete_dataset_endpoint(
    project_id: UUID,
    delete_data: DatasetDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    """
    Delete datasets.

    This endpoint allows users to delete multiple datasets at once.
    This action cannot be undone.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        organization_id = resolve_organization_id(session, project_id)
        for dataset_id in delete_data.dataset_ids:
            if not check_dataset_belongs_to_project(session, project_id, dataset_id):
                raise QADatasetNotInProjectError(project_id, dataset_id)
        deleted_count = delete_datasets_service(session, organization_id, delete_data)
        return {"message": f"Deleted {deleted_count} datasets successfully"}
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except QADatasetNotInProjectError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Dataset {e.dataset_id} is not associated with project {project_id}",
        ) from e


# ── Deprecated custom columns ────────────────────────────────────────

@router.get(
    "/projects/{project_id}/qa/datasets/{dataset_id}/custom-columns",
    deprecated=True,
    response_model=List[QAColumnResponse],
    summary="Get Custom Columns for Dataset",
    tags=["Quality Assurance"],
)
def get_columns_by_dataset_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[QAColumnResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_qa_columns_by_dataset_project_service(session, project_id, dataset_id)
    except QADatasetNotInProjectError as e:
        LOGGER.error(
            f"Failed to get columns for dataset {dataset_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get columns for dataset {dataset_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/custom-columns",
    deprecated=True,
    response_model=QAColumnResponse,
    summary="Add Custom Column to Dataset",
    tags=["Quality Assurance"],
)
def add_column_to_dataset_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    column_name: str = Body(..., embed=True),
) -> QAColumnResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_qa_column_project_service(session, project_id, dataset_id, column_name)
    except QADatasetNotInProjectError as e:
        LOGGER.error(f"Failed to add column to dataset {dataset_id} for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to add column to dataset {dataset_id} for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/projects/{project_id}/qa/datasets/{dataset_id}/custom-columns/{column_id}",
    deprecated=True,
    response_model=QAColumnResponse,
    summary="Rename Custom Column",
    tags=["Quality Assurance"],
)
def rename_column_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    column_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    column_name: str = Body(..., embed=True),
) -> QAColumnResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return rename_qa_column_project_service(session, project_id, dataset_id, column_id, column_name)
    except QADatasetNotInProjectError as e:
        LOGGER.error(
            f"Failed to rename column {column_id} in dataset {dataset_id} for project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except QAColumnNotFoundError as e:
        LOGGER.error(
            f"Failed to rename column {column_id} in dataset {dataset_id} for project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to rename column {column_id} in dataset {dataset_id} for project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/projects/{project_id}/qa/datasets/{dataset_id}/custom-columns/{column_id}",
    deprecated=True,
    summary="Delete Custom Column",
    tags=["Quality Assurance"],
)
def delete_column_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    column_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return delete_qa_column_project_service(session, project_id, dataset_id, column_id)
    except QADatasetNotInProjectError as e:
        LOGGER.error(
            f"Failed to delete column {column_id} from dataset {dataset_id} for project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except QAColumnNotFoundError as e:
        LOGGER.error(
            f"Failed to delete column {column_id} from dataset {dataset_id} for project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to delete column {column_id} from dataset {dataset_id} for project {project_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


# ── Deprecated entries, CSV import/export ────────────────────────────

@router.get(
    "/projects/{project_id}/qa/datasets/{dataset_id}/entries",
    deprecated=True,
    response_model=PaginatedInputGroundtruthResponse,
    summary="Get Input-Groundtruth Entries by Dataset",
    tags=["Quality Assurance"],
)
def get_inputs_groundtruths_by_dataset_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(100, ge=1, le=1000, description="Number of items per page"),
) -> PaginatedInputGroundtruthResponse:
    """
    Get all input-groundtruth entries for a dataset WITHOUT outputs.

    This endpoint returns only the base input-groundtruth pairs for a dataset.
    Use the /outputs endpoint to get outputs for a specific graph_runner.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_inputs_groundtruths_with_version_outputs_service(session, dataset_id, page, page_size)
    except ValueError as e:
        LOGGER.error(f"Failed to get input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/projects/{project_id}/qa/datasets/{dataset_id}/outputs",
    deprecated=True,
    response_model=Dict[UUID, str],
    summary="Get Outputs for a Graph Runner",
    tags=["Quality Assurance"],
)
def get_outputs_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    graph_runner_id: UUID = Query(..., description="Graph runner ID to get outputs for"),
) -> Dict[UUID, str]:
    """
    Get outputs for a specific graph_runner.

    Returns a dictionary mapping input_id (UUID) to output (string) for the specified graph_runner.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_outputs_by_graph_runner_service(session, dataset_id, graph_runner_id)
    except ValueError as e:
        LOGGER.error(
            f"Failed to get outputs for graph runner {graph_runner_id} and dataset {dataset_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get outputs for graph runner {graph_runner_id} and dataset {dataset_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/entries",
    deprecated=True,
    response_model=InputGroundtruthResponseList,
    summary="Create Input-Groundtruth Entries",
    tags=["Quality Assurance"],
)
def create_input_groundtruth_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    input_groundtruth_data: InputGroundtruthCreateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> InputGroundtruthResponseList:
    """
    Create input-groundtruth entries.

    This endpoint allows users to create multiple input-groundtruth pairs for quality assurance purposes.
    All entries will be associated with the specified dataset.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_inputs_groundtruths_service(session, dataset_id, input_groundtruth_data)
    except (QADuplicatePositionError, QAPartialPositionError) as e:
        LOGGER.error(f"Failed to create input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(f"Failed to create input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/projects/{project_id}/qa/datasets/{dataset_id}/entries",
    deprecated=True,
    response_model=InputGroundtruthResponseList,
    summary="Update Input-Groundtruth Entries",
    tags=["Quality Assurance"],
)
def update_input_groundtruth_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    input_groundtruth_data: InputGroundtruthUpdateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> InputGroundtruthResponseList:
    """
    Update input-groundtruth entries.

    This endpoint allows users to update multiple input-groundtruth pairs.
    Only the fields provided in the request will be updated.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return update_inputs_groundtruths_service(session, dataset_id, input_groundtruth_data)
    except ValueError as e:
        LOGGER.error(f"Failed to update input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to update input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/projects/{project_id}/qa/datasets/{dataset_id}/entries",
    deprecated=True,
    summary="Delete Input-Groundtruth Entries",
    tags=["Quality Assurance"],
)
def delete_input_groundtruth_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    delete_data: InputGroundtruthDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    """
    Delete input-groundtruth entries.

    This endpoint allows users to delete multiple input-groundtruth pairs at once.
    This action cannot be undone.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        deleted_count = delete_inputs_groundtruths_service(session, dataset_id, delete_data)
        return {"message": f"Deleted {deleted_count} input-groundtruth entries successfully"}
    except ValueError as e:
        LOGGER.error(f"Failed to delete input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/entries/from-history",
    deprecated=True,
    response_model=List[InputGroundtruthResponse],
    summary="Create Entry from History",
    tags=["Quality Assurance"],
)
async def create_entry_from_history(
    project_id: UUID,
    dataset_id: UUID,
    trace_id: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[InputGroundtruthResponse]:
    try:
        return save_conversation_to_groundtruth_service(
            session=session,
            trace_id=trace_id,
            dataset_id=dataset_id,
        )
    except ValueError as e:
        LOGGER.error(f"Failed to save trace {trace_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/export",
    deprecated=True,
    summary="Export QA Data to CSV",
    tags=["Quality Assurance"],
)
def export_qa_data_to_csv_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    graph_runner_id: UUID = Query(..., description="Graph runner ID to filter outputs"),
) -> Response:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    csv_content = export_qa_data_to_csv_service(session, dataset_id, graph_runner_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"qa_export_{dataset_id}_{timestamp}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/import",
    deprecated=True,
    response_model=InputGroundtruthResponseList,
    summary="Import QA Data from CSV",
    tags=["Quality Assurance"],
)
async def import_qa_data_from_csv_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    file: Annotated[UploadFile, File(..., description="CSV file to import")],
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> InputGroundtruthResponseList:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    await file.seek(0)

    try:
        organization_id = resolve_organization_id(session, project_id)
        result = import_qa_data_from_csv_service(
            session=session,
            organization_id=organization_id,
            dataset_id=dataset_id,
            csv_file=file.file,
        )
        return result
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (
        CSVEmptyFileError,
        CSVInvalidJSONError,
        CSVMissingDatasetColumnError,
        CSVNonUniquePositionError,
        CSVInvalidPositionError,
    ) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except QADatasetNotInProjectError as e:
        LOGGER.error(
            f"Failed to import QA data for dataset {dataset_id} in project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to import QA data for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
