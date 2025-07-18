import logging
import inspect

import requests

from ada_backend.schemas.ingestion_task_schema import IngestionTaskUpdate
from ada_backend.database import models as db
from ada_backend.schemas.source_schema import DataSourceSchema
from data_ingestion.utils import sanitize_filename
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.storage_service.local_service import SQLLocalService
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)


def get_sanitize_names(source_name: str, organization_id: str) -> tuple[str, str, str]:
    sanitize_source_name = sanitize_filename(source_name)
    sanitize_organization_id = sanitize_filename(organization_id)
    schema_name = f"org_{sanitize_organization_id}"
    table_name = f"{sanitize_source_name}_table"
    qdrant_collection_name = f"{sanitize_organization_id}_{sanitize_source_name}_collection"
    return (
        schema_name,
        table_name,
        qdrant_collection_name,
    )


def check_signature(fn: callable, required_params: list[str]):
    sig = inspect.signature(fn)
    fn_params = list(sig.parameters.keys())
    missing = [p for p in required_params if p not in fn_params]
    if missing:
        raise ValueError(
            f"Function {fn.__name__} is missing required parameters: {', '.join(missing)}. "
            f"Expected parameters: {', '.join(required_params)}"
        )


def update_ingestion_task(
    organization_id: str,
    ingestion_task: IngestionTaskUpdate,
) -> None:
    """Update the status of an ingestion task in the database."""
    try:
        response = requests.patch(
            f"{str(settings.ADA_URL)}/ingestion_task/{organization_id}",
            json=ingestion_task.model_dump(mode="json"),
            headers={
                "x-ingestion-api-key": settings.INGESTION_API_KEY,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
    except Exception as e:
        LOGGER.error(f"Failed to update ingestion task: {str(e)}")
        raise requests.exceptions.RequestException(
            f"Failed to update ingestion task for organization {organization_id}: {str(e)}"
        ) from e


def create_source(
    organization_id: str,
    source_data: DataSourceSchema,
) -> None:
    """Create a source in the database."""

    try:
        response = requests.post(
            f"{str(settings.ADA_URL)}/sources/{organization_id}",
            json=source_data.model_dump(mode="json"),
            headers={
                "x-ingestion-api-key": settings.INGESTION_API_KEY,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        LOGGER.info(f"Successfully created source for organization {organization_id}")
        return response.json()
    except Exception as e:
        LOGGER.error(f"Failed to create source: {str(e)}")
        raise requests.exceptions.RequestException(
            f"Failed to create source for organization {organization_id}: "
            f"{str(e)} with the data {source_data.model_dump(mode='json')}"
        ) from e


def upload_source(
    source_name: str,
    organization_id: str,
    task_id: str,
    source_type: db.SourceType,
    qdrant_schema: QdrantCollectionSchema,
    ingestion_function: callable,
    replace_existing: bool = False,
) -> None:
    check_signature(
        ingestion_function,
        required_params=[
            "db_service",
            "qdrant_service",
            "storage_schema_name",
            "storage_table_name",
            "qdrant_collection_name",
        ],
    )
    if settings.INGESTION_DB_URL is None:
        raise ValueError("INGESTION_DB_URL is not set")
    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    schema_name, table_name, qdrant_collection_name = get_sanitize_names(
        source_name=source_name,
        organization_id=organization_id,
    )

    ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.FAILED,
    )
    embedding_service = EmbeddingService(
        provider="openai",
        model_name="text-embedding-3-large",
        trace_manager=TraceManager(project_name="ingestion"),
    )
    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
    )

    if not replace_existing and db_service.schema_exists(schema_name=schema_name):
        if db_service.table_exists(table_name=table_name, schema_name=schema_name):
            LOGGER.error(f"Source {source_name} already exists db in {schema_name}")
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=ingestion_task,
            )
            return
    elif not replace_existing and qdrant_service.collection_exists(qdrant_collection_name):
        LOGGER.error(f"Source {source_name} already exists in Qdrant")
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return

    try:
        ingestion_function(
            db_service=db_service,
            qdrant_service=qdrant_service,
            storage_schema_name=schema_name,
            storage_table_name=table_name,
            qdrant_collection_name=qdrant_collection_name,
            replace_existing=replace_existing,
        )
    except Exception as e:
        LOGGER.error(f"Failed to get data from the database: {str(e)}")
        ingestion_task = IngestionTaskUpdate(
            id=task_id,
            source_name=source_name,
            source_type=source_type,
            status=db.TaskStatus.FAILED,
        )
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return

    source_data = DataSourceSchema(
        name=source_name,
        type=source_type,
        database_schema=schema_name,
        database_table_name=table_name,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_schema=qdrant_schema.to_dict(),
        embedding_model_reference=f"{embedding_service._provider}:{embedding_service._model_name}",
    )
    LOGGER.info(f"Creating source {source_name} for organization {organization_id} in database")
    source_id = create_source(
        organization_id=organization_id,
        source_data=source_data,
    )

    ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_id=source_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.COMPLETED,
    )

    LOGGER.info(f" Update status {source_name} source for organization {organization_id} in database")
    update_ingestion_task(
        organization_id=organization_id,
        ingestion_task=ingestion_task,
    )
    LOGGER.info(f"Successfully ingested {source_name} source for organization {organization_id}")
