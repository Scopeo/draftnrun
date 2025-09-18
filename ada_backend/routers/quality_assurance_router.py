from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
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
from ada_backend.services.quality_assurance_service import (
    create_inputs_groundtruths_service,
    update_inputs_groundtruths_service,
    delete_inputs_groundtruths_service,
    get_inputs_groundtruths_with_version_outputs_service,
    run_qa_service,
    create_datasets_service,
    update_dataset_service,
    delete_datasets_service,
    get_datasets_by_project_service,
)
from ada_backend.database.setup_db import get_db
from ada_backend.database.models import EnvType

router = APIRouter(tags=["QualityAssurance"])


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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


# Input Groundtruth endpoints
@router.get(
    "/projects/{project_id}/qa/{dataset_id}/entries",
    response_model=PaginatedInputGroundtruthResponse,
    summary="Get Input-Groundtruth Entries by Dataset with Version Outputs",
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
    version: EnvType = Query(None, description="Version to filter by (draft or production, optional)"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(100, ge=1, le=1000, description="Number of items per page"),
) -> PaginatedInputGroundtruthResponse:
    """
    Get all input-groundtruth entries for a dataset with version outputs using LEFT JOIN.

    This endpoint allows users to retrieve input-groundtruth pairs specific to a dataset
    for quality assurance purposes. The data is paginated to handle large datasets efficiently.

    If a version is specified (draft or production), it will filter the results to show outputs
    for that specific version.
    If no version is specified, it will show all input-groundtruth entries with their associated outputs.
    Output and version fields will be null if no matching version output is found.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_inputs_groundtruths_with_version_outputs_service(session, dataset_id, version, page, page_size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post(
    "/projects/{project_id}/qa/{dataset_id}/entries",
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.patch(
    "/projects/{project_id}/qa/{dataset_id}/entries",
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
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.delete(
    "/projects/{project_id}/qa/{dataset_id}/entries",
    summary="Delete Input-Groundtruth Entries",
    tags=["Quality Assurance"],
)
def delete_input_groundtruth_endpoint(
    project_id: UUID,
    dataset_id: UUID,
    delete_data: InputGroundtruthDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.USER.value)),
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


# QA Run endpoint
@router.post(
    "/projects/{project_id}/qa/{dataset_id}/run",
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
    Run QA process on multiple inputs from a dataset.

    This endpoint allows users to run a project on specific input entries from a dataset.
    The project will be executed using the specified version (draft or production).
    Results are stored in the VersionOutput table with the specified version.

    The input and output fields are stored as strings but can be easily cast to JSON
    for function processing when needed.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return await run_qa_service(session, project_id, dataset_id, run_request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
