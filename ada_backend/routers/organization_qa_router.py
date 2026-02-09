import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.dataset_schema import (
    DatasetCreateList,
    DatasetDeleteList,
    DatasetListResponse,
    DatasetResponse,
)
from ada_backend.schemas.input_groundtruth_schema import (
    InputGroundtruthCreateList,
    InputGroundtruthDeleteList,
    InputGroundtruthResponseList,
    InputGroundtruthUpdateList,
    PaginatedInputGroundtruthResponse,
)
from ada_backend.schemas.llm_judges_schema import (
    LLMJudgeCreate,
    LLMJudgeResponse,
    LLMJudgeUpdate,
)
from ada_backend.services.errors import LLMJudgeNotFound
from ada_backend.services.qa.llm_judges_service import (
    create_llm_judge_for_organization_service,
    delete_llm_judges_from_organization_service,
    get_llm_judges_by_organization_service,
    update_llm_judge_in_organization_service,
)
from ada_backend.services.qa.qa_error import (
    QADuplicatePositionError,
    QAPartialPositionError,
)
from ada_backend.services.qa.quality_assurance_service import (
    create_datasets_for_organization_service,
    create_inputs_groundtruths_service,
    delete_datasets_from_organization_service,
    delete_inputs_groundtruths_service,
    get_datasets_by_organization_service,
    get_inputs_groundtruths_with_version_outputs_service,
    update_dataset_in_organization_service,
    update_inputs_groundtruths_service,
)

router = APIRouter(tags=["Organization Quality Assurance"])
LOGGER = logging.getLogger(__name__)


# Dataset endpoints
@router.get(
    "/organizations/{organization_id}/qa/datasets",
    response_model=List[DatasetResponse],
    summary="Get Datasets by Organization",
    tags=["Organization Quality Assurance"],
)
def get_datasets_by_organization_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[DatasetResponse]:
    """
    Get all datasets for an organization.

    This endpoint allows users to retrieve all datasets associated with a specific organization
    for quality assurance purposes.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_datasets_by_organization_service(session, organization_id)
    except ValueError as e:
        LOGGER.error(f"Failed to get datasets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to get datasets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/organizations/{organization_id}/qa/datasets",
    response_model=DatasetListResponse,
    summary="Create Datasets for Organization",
    tags=["Organization Quality Assurance"],
)
def create_dataset_for_organization_endpoint(
    organization_id: UUID,
    dataset_data: DatasetCreateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> DatasetListResponse:
    """
    Create datasets for an organization.

    This endpoint allows users to create multiple datasets for quality assurance purposes.
    All datasets will be associated with the specified organization.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_datasets_for_organization_service(session, organization_id, dataset_data)
    except ValueError as e:
        LOGGER.error(f"Failed to create datasets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create datasets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}",
    response_model=DatasetResponse,
    summary="Update Dataset in Organization",
    tags=["Organization Quality Assurance"],
)
def update_dataset_in_organization_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    dataset_name: str,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> DatasetResponse:
    """
    Update dataset in an organization.

    This endpoint allows users to update a single dataset.
    Only the fields provided in the request will be updated.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return update_dataset_in_organization_service(session, organization_id, dataset_id, dataset_name)
    except ValueError as e:
        LOGGER.error(f"Failed to update dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to update dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/organizations/{organization_id}/qa/datasets",
    summary="Delete Datasets from Organization",
    tags=["Organization Quality Assurance"],
)
def delete_datasets_from_organization_endpoint(
    organization_id: UUID,
    delete_data: DatasetDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    """
    Delete datasets from an organization.

    This endpoint allows users to delete multiple datasets at once.
    This action cannot be undone.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        deleted_count = delete_datasets_from_organization_service(session, organization_id, delete_data)
        return {"message": f"Deleted {deleted_count} datasets successfully"}
    except ValueError as e:
        LOGGER.error(f"Failed to delete datasets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete datasets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# Input Groundtruth endpoints (dataset entries)
@router.get(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
    response_model=PaginatedInputGroundtruthResponse,
    summary="Get Input-Groundtruth Entries by Dataset",
    tags=["Organization Quality Assurance"],
)
def get_inputs_groundtruths_by_dataset_in_organization_endpoint(
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


@router.post(
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
    response_model=InputGroundtruthResponseList,
    summary="Create Input-Groundtruth Entries",
    tags=["Organization Quality Assurance"],
)
def create_input_groundtruth_in_organization_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    input_groundtruth_data: InputGroundtruthCreateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
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
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
    response_model=InputGroundtruthResponseList,
    summary="Update Input-Groundtruth Entries",
    tags=["Organization Quality Assurance"],
)
def update_input_groundtruth_in_organization_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    input_groundtruth_data: InputGroundtruthUpdateList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
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
    "/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
    summary="Delete Input-Groundtruth Entries",
    tags=["Organization Quality Assurance"],
)
def delete_input_groundtruth_in_organization_endpoint(
    organization_id: UUID,
    dataset_id: UUID,
    delete_data: InputGroundtruthDeleteList,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
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


# LLM Judge endpoints
@router.get(
    "/organizations/{organization_id}/qa/llm-judges",
    response_model=List[LLMJudgeResponse],
    summary="Get LLM Judges by Organization",
    tags=["Organization Quality Assurance"],
)
def get_llm_judges_by_organization_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> List[LLMJudgeResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_llm_judges_by_organization_service(session=session, organization_id=organization_id)
    except Exception as e:
        LOGGER.error(f"Failed to get LLM judges for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/organizations/{organization_id}/qa/llm-judges",
    response_model=LLMJudgeResponse,
    summary="Create LLM Judge for Organization",
    tags=["Organization Quality Assurance"],
)
def create_llm_judge_for_organization_endpoint(
    organization_id: UUID,
    judge_data: LLMJudgeCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_llm_judge_for_organization_service(
            session=session, organization_id=organization_id, judge_data=judge_data
        )
    except ValueError as e:
        LOGGER.error(f"Failed to create LLM judge for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to create LLM judge for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/organizations/{organization_id}/qa/llm-judges/{judge_id}",
    response_model=LLMJudgeResponse,
    summary="Update LLM Judge in Organization",
    tags=["Organization Quality Assurance"],
)
def update_llm_judge_in_organization_endpoint(
    organization_id: UUID,
    judge_id: UUID,
    judge_data: LLMJudgeUpdate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> LLMJudgeResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return update_llm_judge_in_organization_service(
            session=session,
            organization_id=organization_id,
            judge_id=judge_id,
            judge_data=judge_data,
        )
    except LLMJudgeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        LOGGER.error(
            f"Failed to update LLM judge {judge_id} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to update LLM judge {judge_id} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/organizations/{organization_id}/qa/llm-judges",
    status_code=204,
    summary="Delete LLM Judges from Organization",
    tags=["Organization Quality Assurance"],
)
def delete_llm_judges_from_organization_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    judge_ids: List[UUID] = Query(...),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        delete_llm_judges_from_organization_service(
            session=session, organization_id=organization_id, judge_ids=judge_ids
        )
        return None
    except ValueError as e:
        LOGGER.error(f"Failed to delete LLM judges for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(f"Failed to delete LLM judges for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
