from typing import Annotated, Dict, List
from uuid import UUID
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.input_groundtruth_schema import (
    InputGroundtruthCreateList,
    InputGroundtruthUpdateList,
    InputGroundtruthDeleteList,
    InputGroundtruthResponseList,
    PaginatedInputGroundtruthResponse,
    QARunRequest,
    QARunResponse,
    InputGroundtruthResponse,
)
from ada_backend.schemas.dataset_schema import (
    DatasetCreateList,
    DatasetResponse,
    DatasetDeleteList,
    DatasetListResponse,
)
from ada_backend.routers.auth_router import (
    user_has_access_to_project_dependency,
    UserRights,
)
from ada_backend.services.qa.quality_assurance_service import (
    create_inputs_groundtruths_service,
    update_inputs_groundtruths_service,
    delete_inputs_groundtruths_service,
    get_inputs_groundtruths_with_version_outputs_service,
    get_outputs_by_graph_runner_service,
    run_qa_service,
    create_datasets_service,
    update_dataset_service,
    delete_datasets_service,
    get_datasets_by_project_service,
    save_conversation_to_groundtruth_service,
    export_qa_data_to_csv_service,
    import_qa_data_from_csv_service,
)
from ada_backend.services.qa.qa_error import (
    CSVEmptyFileError,
    CSVInvalidJSONError,
    CSVMissingColumnError,
    CSVExportError,
)
from ada_backend.database.setup_db import get_db

router = APIRouter(tags=["Quality Assurance"])
LOGGER = logging.getLogger(__name__)


# Dataset endpoints
@router.get(
    "/projects/{project_id}/qa/datasets",
    response_model=List[DatasetResponse],
    summary="Get Datasets by Project",
    tags=["Quality Assurance"],
)
def get_datasets_by_project_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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

    try:
        return get_datasets_by_project_service(session, project_id)
    except ValueError as e:
        LOGGER.error(f"Failed to get datasets for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get datasets for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/datasets",
    response_model=DatasetListResponse,
    summary="Create Datasets",
    tags=["Quality Assurance"],
)
def create_dataset_endpoint(
    project_id: UUID,
    dataset_data: DatasetCreateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
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
        return create_datasets_service(session, project_id, dataset_data)
    except ValueError as e:
        LOGGER.error(f"Failed to create datasets for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create datasets for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/projects/{project_id}/qa/datasets/{dataset_id}",
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
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
        return update_dataset_service(session, project_id, dataset_id, dataset_name)
    except ValueError as e:
        LOGGER.error(f"Failed to update dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to update dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/projects/{project_id}/qa/datasets",
    summary="Delete Datasets",
    tags=["Quality Assurance"],
)
def delete_dataset_endpoint(
    project_id: UUID,
    delete_data: DatasetDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
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
        deleted_count = delete_datasets_service(session, project_id, delete_data)
        return {"message": f"Deleted {deleted_count} datasets successfully"}
    except ValueError as e:
        LOGGER.error(f"Failed to delete datasets for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete datasets for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# Input Groundtruth endpoints
@router.get(
    "/projects/{project_id}/qa/datasets/{dataset_id}/entries",
    response_model=PaginatedInputGroundtruthResponse,
    summary="Get Input-Groundtruth Entries by Dataset",
    tags=["Quality Assurance"],
)
def get_inputs_groundtruths_by_dataset_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
    response_model=Dict[UUID, str],
    summary="Get Outputs for a Graph Runner",
    tags=["Quality Assurance"],
)
def get_outputs_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
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
    except ValueError as e:
        LOGGER.error(f"Failed to create input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create input-groundtruth entries for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/projects/{project_id}/qa/datasets/{dataset_id}/entries",
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
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
    summary="Delete Input-Groundtruth Entries",
    tags=["Quality Assurance"],
)
def delete_input_groundtruth_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    delete_data: InputGroundtruthDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value)),
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


# QA Run endpoint
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> QARunResponse:
    """
    Run QA process on inputs from a dataset.

    This endpoint allows users to run a project on input entries from a dataset.
    You can either run on specific entries by providing input_ids, or run on all
    entries in the dataset by setting run_all=True.

    The project will be executed using the specified graph_runner_id to run a specific version.
    Results are stored in the VersionOutput table.

    Parameters:
    - graph_runner_id: Specific graph runner ID to execute (required)
    - input_ids: List of specific input IDs to run (optional if run_all=True)
    - run_all: Boolean flag to run on all entries in the dataset (optional, default=False)

    Note:
    - You must specify either input_ids OR set run_all=True, but not both.

    The input and output fields are stored as strings but can be easily cast to JSON
    for function processing when needed.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return await run_qa_service(session, project_id, dataset_id, run_request)
    except ValueError as e:
        LOGGER.error(
            f"Failed to run QA process on dataset {dataset_id} for project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to run QA process on dataset {dataset_id} for project {project_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/entries/from-history",
    response_model=List[InputGroundtruthResponse],
    summary="Create Entry from History",
    tags=["Quality Assurance"],
)
async def create_entry_from_history(
    project_id: UUID,
    dataset_id: UUID,
    trace_id: str,
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
    except Exception as e:
        LOGGER.error(f"Failed to save trace {trace_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/projects/{project_id}/qa/datasets/{dataset_id}/export",
    summary="Export QA Data to CSV",
    tags=["Quality Assurance"],
)
def export_qa_data_to_csv_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
    graph_runner_id: UUID = Query(..., description="Graph runner ID to filter outputs"),
) -> Response:

    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        csv_content = export_qa_data_to_csv_service(session, dataset_id, graph_runner_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"qa_export_{dataset_id}_{timestamp}.csv"

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except CSVExportError as e:
        LOGGER.warning(f"CSV export failed for dataset {dataset_id}: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/projects/{project_id}/qa/datasets/{dataset_id}/import",
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
    ],
    session: Session = Depends(get_db),
) -> InputGroundtruthResponseList:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        await file.seek(0)

        result = import_qa_data_from_csv_service(
            session=session,
            dataset_id=dataset_id,
            csv_file=file.file,
        )
        return result

    except (
        CSVEmptyFileError,
        CSVInvalidJSONError,
        CSVMissingColumnError,
    ) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to import QA data for dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
