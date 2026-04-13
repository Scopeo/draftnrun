import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional, Union

import httpx

from engine.components.types import SourceChunk
from engine.datetime_utils import make_naive_utc, parse_datetime
from engine.llm_services.llm_service import EmbeddingService
from settings import settings

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_CHUNKS = 10
MAX_BATCH_SIZE_FOR_CHUNK_UPLOAD = 50
DEFAULT_TIMEOUT = 20.0
SOURCE_ID_COLUMN_NAME = "source_id"
BM25_MODEL = "Qdrant/bm25"


class FieldSchema(Enum):
    KEYWORD = "keyword"
    DATETIME = "datetime"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "bool"


class SearchMode(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


def map_internal_type_to_qdrant_field_schema(internal_type: str) -> FieldSchema:
    """Map internal DBDefinition types to Qdrant FieldSchema types."""
    type_mapping = {
        "DATETIME": FieldSchema.DATETIME,
        "INTEGER": FieldSchema.INTEGER,
        "FLOAT": FieldSchema.FLOAT,
        "BOOLEAN": FieldSchema.BOOLEAN,
        "VARCHAR": FieldSchema.KEYWORD,
        "TEXT": FieldSchema.KEYWORD,
        "VARIANT": FieldSchema.KEYWORD,
        "ARRAY": FieldSchema.KEYWORD,
    }
    return type_mapping.get(internal_type, FieldSchema.KEYWORD)


def map_sql_type_to_qdrant_field_schema(sql_type: str) -> FieldSchema:
    """Map a SQL column type string (e.g. from SQLAlchemy reflection) to a Qdrant FieldSchema."""
    t = sql_type.upper()
    if "TIMESTAMP" in t or "DATETIME" in t or t == "DATE":
        return FieldSchema.DATETIME
    if "INT" in t:
        return FieldSchema.INTEGER
    if any(x in t for x in ("DOUBLE", "FLOAT", "NUMERIC", "DECIMAL", "REAL")):
        return FieldSchema.FLOAT
    if "BOOL" in t:
        return FieldSchema.BOOLEAN
    return FieldSchema.KEYWORD


@dataclass
class QdrantCollectionSchema:
    """
    Dataclass model for storing the names of the fields in a Qdrant collection.

    Args:
        - chunk_id_field (str): The name of the column in the Qdrant collection
        that contains the chunk id.
        - content_field (str): The name of the column in the Qdrant collection
        that contains the chunk content.
        - file_id_field (Optional[str]): The name of the column that contains the
        file id from which the chunks originate.
        - url_field (Optional[str]): The name of the column that contains the
        url from which the chunks originate.
        - last_edited_ts_field (Optional[str]): The name of the column that contains
            the timestamp of the last edit of the chunk.
        - metadata_fields_to_keep (Optional[set[str]]): A set of metadata field names
        to keep. If None, only the fields listed above will be kept.
    """

    chunk_id_field: str
    content_field: str
    file_id_field: str
    url_id_field: Optional[str] = None
    last_edited_ts_field: Optional[str] = None  # To keep compatibility with Juno data
    source_id_field: Optional[str] = None  # Field to track which source a chunk belongs to
    metadata_fields_to_keep: Optional[set[str]] = None  # To keep compatibility with Juno data
    metadata_field_types: Optional[dict[str, str]] = None

    def __post_init__(self):
        """
        Validate field names after initialization.
        """
        for field_name, field_value in self.__dict__.items():
            if field_value is None:
                continue
            if isinstance(field_value, str):
                values = [field_value]
            else:
                values = field_value
            for value in values:
                if not value.islower():
                    LOGGER.warning(
                        f"For field '{field_name}', the value '{value}' in QdrantCollectionSchema is not lowercase."
                    )

    def to_dict(self) -> dict:
        """
        Convert the QdrantCollectionSchema to a dictionary.
        Set fields are converted to lists for better JSON serialization.

        Returns:
            dict: Dictionary representation of the schema
        """
        schema_dict = {}
        for field, value in self.__dict__.items():
            if isinstance(value, set):
                schema_dict[field] = list(value) if value is not None else None
            else:
                schema_dict[field] = value
        return schema_dict


class QdrantService:
    def __init__(
        self,
        qdrant_api_key: str,
        qdrant_cluster_url: str,
        default_schema: QdrantCollectionSchema,
        embedding_service: Optional[EmbeddingService] = None,
        max_chunks_to_add: int = MAX_BATCH_SIZE_FOR_CHUNK_UPLOAD,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the Qdrant service.

        Args:
            - qdrant_api_key (str): The API key for the Qdrant service.
            - qdrant_cluster_url (str): The URL of the Qdrant cluster.
            - collection_name (str): The name of the collection in Qdrant.
            - collection_schema (QdrantCollectionSchema): The schema configuration for the chunk data.
        """

        self._headers = {"api-key": qdrant_api_key, "Content-Type": "application/json"}
        self._base_url = qdrant_cluster_url
        self._embedding_service = embedding_service
        self._max_chunks_to_add = max_chunks_to_add
        self._timeout = timeout

        self.default_schema = default_schema
        self._schemas: dict[str, QdrantCollectionSchema] = {}

    def register_schema(self, collection_name: str, schema: QdrantCollectionSchema):
        """
        Register a specific schema for a given collection.

        Args:
            collection_name (str): The name of the collection.
            schema (QdrantCollectionSchema): The schema for the collection.
        """
        self._schemas[collection_name] = schema

    def _get_schema(self, collection_name: str) -> QdrantCollectionSchema:
        """
        Retrieve the schema for a given collection, or use the default schema if not registered.

        Args:
            collection_name (str): The name of the collection.
        """
        return self._schemas.get(collection_name, self.default_schema)

    @staticmethod
    def _should_update(incoming_ts_raw, existing_ts_raw) -> bool:
        incoming_dt = parse_datetime(incoming_ts_raw)
        existing_dt = parse_datetime(existing_ts_raw)
        if incoming_dt is not None and existing_dt is not None:
            return make_naive_utc(incoming_dt) > make_naive_utc(existing_dt)
        return False

    @classmethod
    def from_defaults(
        cls,
        embedding_service: Optional[EmbeddingService] = None,
        default_collection_schema: Optional[QdrantCollectionSchema] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> "QdrantService":
        """
        Initialize the Qdrant service using the default settings from the environment variables.
        """
        if not default_collection_schema:
            default_collection_schema = QdrantCollectionSchema(
                chunk_id_field="chunk_id",
                content_field="content",
                file_id_field="file_id",
                url_id_field="url",
                last_edited_ts_field="last_edited_ts",
            )
        if not settings.QDRANT_API_KEY:
            raise ValueError("QDRANT_API_KEY environment variable is not set.")
        if not settings.QDRANT_CLUSTER_URL:
            raise ValueError("QDRANT_CLUSTER_URL environment variable is not set.")
        return cls(
            qdrant_api_key=settings.QDRANT_API_KEY,
            qdrant_cluster_url=settings.QDRANT_CLUSTER_URL,
            default_schema=default_collection_schema,
            embedding_service=embedding_service,
            timeout=timeout,
        )

    async def _send_request_async(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict] = None,
    ) -> dict:
        """
        Send an async request to the Qdrant API.

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE).
            endpoint (str): The Qdrant API endpoint (relative to the base URL).
            payload (Optional[dict]): The request payload for POST/PUT methods.
            timeout (Optional[float]): Request timeout in seconds. If None, uses instance timeout.

        Returns:
            dict: The JSON response from the API.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method=method, url=f"{self._base_url}/{endpoint}", json=payload, headers=self._headers
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as http_err:
            LOGGER.error(f"HTTP error occurred: {http_err}")
            raise
        except Exception as err:
            LOGGER.error(f"Request error: {err}")
            raise

    def search_vectors(
        self,
        query_vector: list[float],
        collection_name: str,
        filter: Optional[dict] = None,
        **search_params,
    ) -> list[tuple[str, dict]]:
        """
        Search for vectors similar to the given query vector in the Qdrant collection.
        Refer to the Qdrant API documentation for more details:
        https://api.qdrant.tech/api-reference/search/points

        Args:
            query_vector (list[float]): The vector to search for similar vectors in the collection.
            collection_name (str): The name of the collection to search in.
            filter (Optional[dict]): A filter to apply to the search query.
            search_params (dict): Additional search parameters, such as 'limit', etc.

        Returns:
            list[str]: A list of vector IDs from the search results.
        """
        return asyncio.run(self.search_vectors_async(query_vector, collection_name, filter, **search_params))

    async def search_vectors_async(
        self,
        query_vector: list[float],
        collection_name: str,
        filter: Optional[dict] = None,
        **search_params,
    ) -> list[tuple[str, float, dict]]:
        """
        Async version of search_vectors.
        Search for vectors similar to the given query vector in the Qdrant collection.
        Uses the named ``dense`` vector so it works with hybrid collections.
        """
        payload: dict[str, Any] = {
            "query": query_vector,
            "using": "dense",
            "with_payload": True,
            "limit": search_params.pop("limit", DEFAULT_MAX_CHUNKS),
        }
        if filter:
            payload["filter"] = filter
        return await self._query_points_async(collection_name, payload)

    async def _query_points_async(
        self,
        collection_name: str,
        query_payload: dict,
    ) -> list[tuple[str, float, dict]]:
        """Call the /points/query endpoint and return results in the same format as search_vectors_async."""
        response = await self._send_request_async(
            method="POST",
            endpoint=f"collections/{collection_name}/points/query",
            payload=query_payload,
        )
        points = response.get("result", {}).get("points", [])
        return [(point["id"], point["score"], point.get("payload", {})) for point in points]

    async def _search_hybrid_async(
        self,
        query_text: str,
        query_vector: list[float],
        collection_name: str,
        filter: Optional[dict] = None,
        limit: int = DEFAULT_MAX_CHUNKS,
    ) -> list[tuple[str, float, dict]]:
        prefetch_limit = limit * 2
        payload: dict[str, Any] = {
            "prefetch": [
                {
                    "query": {"text": query_text, "model": BM25_MODEL},
                    "using": "sparse",
                    "limit": prefetch_limit,
                },
                {
                    "query": query_vector,
                    "using": "dense",
                    "limit": prefetch_limit,
                },
            ],
            "query": {"fusion": "rrf"},
            "limit": limit,
            "with_payload": True,
        }
        if filter:
            payload["prefetch"][0]["filter"] = filter
            payload["prefetch"][1]["filter"] = filter
        return await self._query_points_async(collection_name, payload)

    async def _search_dense_named_async(
        self,
        query_vector: list[float],
        collection_name: str,
        filter: Optional[dict] = None,
        limit: int = DEFAULT_MAX_CHUNKS,
    ) -> list[tuple[str, float, dict]]:
        payload: dict[str, Any] = {
            "query": query_vector,
            "using": "dense",
            "limit": limit,
            "with_payload": True,
        }
        if filter:
            payload["filter"] = filter
        return await self._query_points_async(collection_name, payload)

    async def _search_sparse_async(
        self,
        query_text: str,
        collection_name: str,
        filter: Optional[dict] = None,
        limit: int = DEFAULT_MAX_CHUNKS,
    ) -> list[tuple[str, float, dict]]:
        payload: dict[str, Any] = {
            "query": {"text": query_text, "model": BM25_MODEL},
            "using": "sparse",
            "limit": limit,
            "with_payload": True,
        }
        if filter:
            payload["filter"] = filter
        return await self._query_points_async(collection_name, payload)

    def get_chunk_data_by_id(
        self,
        vector_ids: list[str],
        collection_name: str,
    ) -> list[dict]:
        """
        Retrieve data for a list of point IDs from the Qdrant collection.
        Refer to the Qdrant API documentation for more details:
        https://api.qdrant.tech/api-reference/points/get-points
        """
        return asyncio.run(self.get_chunk_data_by_id_async(vector_ids, collection_name))

    async def get_chunk_data_by_id_async(
        self,
        vector_ids: list[str],
        collection_name: str,
    ) -> list[dict]:
        """
        Async version of get_chunk_data_by_id.
        Retrieve data for a list of point IDs from the Qdrant collection.
        """
        if not vector_ids:
            raise ValueError("The list of point IDs cannot be empty.")

        payload = {
            "ids": vector_ids,
            "with_payload": True,
            "with_vector": False,
        }

        response = await self._send_request_async(
            method="POST",
            endpoint=f"collections/{collection_name}/points",
            payload=payload,
        )

        return response.get("result", [])

    def _build_vectors(self, input_text: str | list[str]) -> list[list[float]]:
        """Build an embedding vector for the given text using the OpenAI API."""
        return asyncio.run(self._build_vectors_async(input_text))

    async def _build_vectors_async(self, input_text: str | list[str]) -> list[list[float]]:
        """Asynchronously build embedding vectors for the given text using the embedding service."""
        input_embeddings = input_text
        if isinstance(input_text, str):
            input_embeddings = [input_text]
        return [data.embedding for data in await self._embedding_service.embed_text_async(input_embeddings)]

    def apply_date_penalty_to_chunks(
        self,
        vector_results: list[tuple[str, float, dict]],
        metadata_date_key: list[str],
        default_penalty_rate: float,
        chunk_age_penalty_rate: float,
        max_retrieved_chunks_after_penalty: int,
    ) -> list[tuple[str, float, dict]]:
        ordered_chunks = []
        current_year = datetime.today().year
        start_of_year = datetime(current_year, 1, 1)
        for vector_id, score, payload in vector_results:
            # Try each date key in order until we find a valid one
            date = None
            for date_key in metadata_date_key:
                date = payload.get(date_key)
                if date is not None and date:  # Check if not None and not empty
                    break
            if not date:
                penalized_score = default_penalty_rate
            else:
                chunk_date = parse_datetime(date)
                if chunk_date is None:
                    # If we can't parse the date, apply default penalty
                    penalized_score = default_penalty_rate
                else:
                    age = max(0, (start_of_year - chunk_date).days / 365)
                    penalty = min(age * chunk_age_penalty_rate, 5 * chunk_age_penalty_rate)
                    penalized_score = score - penalty
            ordered_chunks.append((vector_id, penalized_score, payload))
        ordered_chunks.sort(key=lambda x: x[1], reverse=True)
        sorted_chunks = ordered_chunks[:max_retrieved_chunks_after_penalty]
        vector_ids, scores, payloads = zip(*sorted_chunks, strict=False)
        return vector_ids, scores, payloads

    def retrieve_similar_chunks(
        self,
        query_text: str,
        collection_name: str,
        limit: int = DEFAULT_MAX_CHUNKS,
        filter: dict = None,
        enable_date_penalty_for_chunks: bool = False,
        chunk_age_penalty_rate: Optional[float] = None,
        default_penalty_rate: Optional[float] = None,
        metadata_date_key: Optional[list[str]] = None,
        max_retrieved_chunks_after_penalty: Optional[int] = None,
        source_schemas: Optional[dict[str, "QdrantCollectionSchema"]] = None,
        search_mode: SearchMode = SearchMode.SEMANTIC,
        **search_params,
    ) -> list[SourceChunk]:
        """
        Search for chunks similar to the given text.
        Additional search parameters can be passed as keyword arguments such as limit, filters, etc.
        """
        return asyncio.run(
            self.retrieve_similar_chunks_async(
                query_text,
                collection_name,
                limit,
                filter,
                enable_date_penalty_for_chunks,
                chunk_age_penalty_rate,
                default_penalty_rate,
                metadata_date_key,
                max_retrieved_chunks_after_penalty,
                source_schemas=source_schemas,
                search_mode=search_mode,
                **search_params,
            )
        )

    async def retrieve_similar_chunks_async(
        self,
        query_text: str,
        collection_name: str,
        limit: int = DEFAULT_MAX_CHUNKS,
        filter: dict = None,
        enable_date_penalty_for_chunks: bool = False,
        chunk_age_penalty_rate: Optional[float] = None,
        default_penalty_rate: Optional[float] = None,
        metadata_date_key: Optional[list[str]] = None,
        max_retrieved_chunks_after_penalty: Optional[int] = None,
        source_schemas: Optional[dict[str, "QdrantCollectionSchema"]] = None,
        search_mode: SearchMode = SearchMode.SEMANTIC,
        **search_params,
    ) -> list[SourceChunk]:
        """
        Async version of retrieve_similar_chunks.
        Search for chunks similar to the given text.
        """
        schema = self._get_schema(collection_name)

        if search_mode == SearchMode.KEYWORD:
            vector_results = await self._search_sparse_async(
                query_text=query_text,
                collection_name=collection_name,
                filter=filter,
                limit=limit,
            )
        elif search_mode == SearchMode.HYBRID:
            query_vector = (await self._build_vectors_async(query_text))[0]
            vector_results = await self._search_hybrid_async(
                query_text=query_text,
                query_vector=query_vector,
                collection_name=collection_name,
                filter=filter,
                limit=limit,
            )
        else:
            query_vector = (await self._build_vectors_async(query_text))[0]
            vector_results = await self._search_dense_named_async(
                query_vector=query_vector,
                collection_name=collection_name,
                filter=filter,
                limit=limit,
            )

        if not vector_results:
            LOGGER.warning(f"No similar vectors found for query: {query_text}")
            return []
        vector_ids, scores, payloads = zip(*vector_results, strict=False)

        LOGGER.debug(f"Retrieved similar vectors with IDs: {vector_ids}")
        if len(vector_ids) == 0:
            LOGGER.warning(f"No document matched the filtering criteria {filter}.")
            return []

        if enable_date_penalty_for_chunks:
            vector_ids, scores, payloads = self.apply_date_penalty_to_chunks(
                vector_results,
                metadata_date_key,
                default_penalty_rate,
                chunk_age_penalty_rate,
                max_retrieved_chunks_after_penalty,
            )

        results = await self.get_chunk_data_by_id_async(collection_name=collection_name, vector_ids=vector_ids)

        chunks: list[SourceChunk] = []
        for result in results:
            if not (chunk_data := result.get("payload")):
                continue

            chunk_schema = schema
            if source_schemas:
                source_id = chunk_data.get(SOURCE_ID_COLUMN_NAME)
                if source_id:
                    chunk_schema = source_schemas.get(source_id, schema)

            content = chunk_data.get(chunk_schema.content_field)
            if not content:
                LOGGER.warning(f"Missing text for chunk: {chunk_data}")
                continue

            if chunk_schema.metadata_fields_to_keep:
                fields_to_keep = (
                    chunk_schema.metadata_fields_to_keep
                    if isinstance(chunk_schema.metadata_fields_to_keep, set)
                    else set(chunk_schema.metadata_fields_to_keep)
                )
                metadata = {key: value for key, value in chunk_data.items() if key in fields_to_keep}
            else:
                standard_fields = set(
                    field
                    for field in (
                        chunk_schema.chunk_id_field,
                        chunk_schema.content_field,
                        chunk_schema.file_id_field,
                        chunk_schema.url_id_field,
                        chunk_schema.last_edited_ts_field,
                        chunk_schema.source_id_field,
                    )
                    if field is not None
                )

                metadata = {k: v for k, v in chunk_data.items() if k not in standard_fields}
            chunks.append(
                SourceChunk(
                    name=chunk_data.get(chunk_schema.chunk_id_field, ""),
                    document_name=chunk_data.get(chunk_schema.file_id_field, ""),
                    content=content,
                    url=str(chunk_data.get(chunk_schema.url_id_field, "")),
                    metadata=metadata,
                )
            )
        return chunks

    def create_index_if_needed(self, collection_name: str, field_name: str, field_schema_type: FieldSchema) -> None:
        return asyncio.run(
            self.create_index_if_needed_async(
                collection_name=collection_name,
                field_name=field_name,
                field_schema_type=field_schema_type,
            )
        )

    async def create_index_if_needed_async(
        self,
        collection_name: str,
        field_name: str,
        field_schema_type: FieldSchema,
    ) -> None:
        """Ensure a payload index exists with the expected type.

        - If missing: create it.
        - If present with same type: no-op.
        - If present with different type: delete and re-create.
        """
        resp = await self._send_request_async(
            method="GET",
            endpoint=f"/collections/{collection_name}",
        )
        payload_schema = (resp.get("result") or {}).get("payload_schema") or {}

        entry = payload_schema.get(field_name)

        if isinstance(entry, dict):
            current_type = entry.get("data_type") or entry.get("type") or entry.get("field_type")
        else:
            current_type = entry

        if current_type is None:
            # No index -> create
            LOGGER.info(
                "Creating payload index '%s' (type=%s) for collection '%s'",
                field_name,
                field_schema_type.value,
                collection_name,
            )

            endpoint = f"/collections/{collection_name}/index"
            payload = {"field_name": field_name, "field_schema": field_schema_type.value}
            await self._send_request_async(method="PUT", endpoint=endpoint, payload=payload)
            return

        if current_type == field_schema_type.value:
            LOGGER.debug(
                "Payload index '%s' already exists with type '%s' in collection '%s'.",
                field_name,
                current_type,
                collection_name,
            )
            return

        LOGGER.warning(
            "Payload index '%s' exists with type '%s' but expected '%s'. Recreating index in collection '%s'.",
            field_name,
            current_type,
            field_schema_type.value,
            collection_name,
        )
        delete_endpoint = f"/collections/{collection_name}/index/{field_name}"
        await self._send_request_async(method="DELETE", endpoint=delete_endpoint)

        create_endpoint = f"/collections/{collection_name}/index"
        payload = {"field_name": field_name, "field_schema": field_schema_type.value}
        await self._send_request_async(method="PUT", endpoint=create_endpoint, payload=payload)

    async def _create_indexes_from_schema(
        self,
        collection_name: str,
        schema: QdrantCollectionSchema,
    ) -> None:
        await self.create_index_if_needed_async(
            collection_name=collection_name,
            field_name=schema.chunk_id_field,
            field_schema_type=FieldSchema.KEYWORD,
        )
        if schema.metadata_fields_to_keep:
            for metadata_field in schema.metadata_fields_to_keep:
                field_type = FieldSchema.KEYWORD  # Default type
                if schema.metadata_field_types and metadata_field in schema.metadata_field_types:
                    internal_type = schema.metadata_field_types[metadata_field]
                    field_type = map_internal_type_to_qdrant_field_schema(internal_type)

                await self.create_index_if_needed_async(
                    collection_name=collection_name,
                    field_name=metadata_field,
                    field_schema_type=field_type,
                )
        if schema.last_edited_ts_field:
            await self.create_index_if_needed_async(
                collection_name=collection_name,
                field_name=schema.last_edited_ts_field,
                field_schema_type=FieldSchema.DATETIME,
            )
        if schema.source_id_field:
            await self.create_index_if_needed_async(
                collection_name=collection_name,
                field_name=schema.source_id_field,
                field_schema_type=FieldSchema.KEYWORD,
            )

    def add_chunks(
        self,
        list_chunks: list[dict[str, Any]],
        collection_name: str,
    ) -> bool:
        """
        Add chunks to the Qdrant collection.

        Args:
            list_chunks (list[dict]): A list of chunks to add to the collection.
            Each chunk is composed of a dictionary of string keys/string values.
            The Qdrant service has a collection schema that defines the fields of the chunks.
            collection_name (str): The name of the collection to add the chunks to.
        Returns:
            str: The status of the operation.
        """
        return asyncio.run(self.add_chunks_async(list_chunks, collection_name))

    async def add_chunks_async(
        self,
        list_chunks: list[dict[str, Any]],
        collection_name: str,
    ) -> bool:
        """
        Async version of add_chunks.
        Add chunks to the Qdrant collection asynchronously.
        """
        schema = self._get_schema(collection_name)

        for i in range(0, len(list_chunks), self._max_chunks_to_add):
            current_chunk_batch = list_chunks[i : i + self._max_chunks_to_add]
            list_embeddings = await self._build_vectors_async([
                chunk[schema.content_field] for chunk in current_chunk_batch
            ])
            metadata_to_keep = set(schema.metadata_fields_to_keep or [])
            url_field = {schema.url_id_field} if schema.url_id_field else {}
            payload_fields = {
                schema.chunk_id_field,
                schema.content_field,
                schema.file_id_field,
                *url_field,
                *metadata_to_keep,
            }
            if schema.last_edited_ts_field:
                payload_fields.add(schema.last_edited_ts_field)
            if schema.source_id_field:
                payload_fields.add(schema.source_id_field)

            list_payloads = []
            for chunk, vector in zip(current_chunk_batch, list_embeddings, strict=False):
                point = {
                    "id": self.get_uuid(self._build_point_id_seed(chunk, schema)),
                    "payload": {field: chunk[field] for field in chunk.keys()},
                    "vector": {
                        "dense": vector,
                        "sparse": {"text": chunk[schema.content_field], "model": BM25_MODEL},
                    },
                }
                list_payloads.append(point)

            if not await self.insert_points_in_collection_async(
                points=list_payloads,
                collection_name=collection_name,
            ):
                LOGGER.error(f"Failed to add chunks {i} to {i + self._max_chunks_to_add}")
                return False
        LOGGER.info(f"Added {len(list_chunks)} chunks to the collection")
        return True

    def delete_chunks(
        self,
        point_ids: list[str],
        id_field: str,
        collection_name: str,
        filter: Optional[dict] = None,
    ) -> bool:
        """Delete chunks from the Qdrant collection based on the list
        of IDs for a given field name."""
        return asyncio.run(self.delete_chunks_async(point_ids, id_field, collection_name, filter))

    async def delete_chunks_async(
        self,
        point_ids: list[str],
        id_field: str,
        collection_name: str,
        filter: Optional[dict] = None,
    ) -> bool:
        """
        Async version of delete_chunks.
        Delete chunks from the Qdrant collection based on the list
        of IDs for a given field name.
        """
        filter_on_qdrant_field = self._combine_filters(
            base_filter=filter,
            additional_filters=[{"should": [{"key": id_field, "match": {"any": point_ids}}]}],
        )
        points = await self.get_points_async(filter=filter_on_qdrant_field, collection_name=collection_name)
        if not points:
            return True
        return await self.delete_points_async(
            collection_name=collection_name,
            point_ids=[point["id"] for point in points],
        )

    @staticmethod
    def get_uuid(string_id: str) -> str:
        """Generate a UUID."""
        namespace = uuid.NAMESPACE_DNS
        return str(uuid.uuid5(namespace, string_id))

    @staticmethod
    def _build_point_id_seed(chunk: dict[str, Any], schema: QdrantCollectionSchema) -> str:
        # TODO: Remove this workaround once chunk_id will be unique uuid
        seed = chunk[schema.chunk_id_field]
        if schema.source_id_field:
            source_id = chunk.get(schema.source_id_field)
            if source_id:
                seed = f"{source_id}:{seed}"
        return seed

    def _build_timestamp_filter(
        self,
        timestamp_filter: str,
        timestamp_column_name: str,
    ) -> Optional[dict]:
        if not timestamp_filter or not timestamp_column_name:
            return None
        # Parse the filter string to extract operator and value
        pattern = r'([><=!]+)\s*["\']?([^"\']+)["\']?'
        match = re.match(pattern, timestamp_filter.strip())

        if not match:
            LOGGER.warning(f"Invalid timestamp filter format: {timestamp_filter}")
            return None

        operator, value = match.groups()
        value = value.strip()

        # Convert operators to Qdrant range operators
        if operator in [">=", "ge"]:
            return {"key": timestamp_column_name, "range": {"gte": value}}
        elif operator in [">", "gt"]:
            return {"key": timestamp_column_name, "range": {"gt": value}}
        elif operator in ["<=", "le"]:
            return {"key": timestamp_column_name, "range": {"lte": value}}
        elif operator in ["<", "lt"]:
            return {"key": timestamp_column_name, "range": {"lt": value}}
        elif operator in ["=", "==", "eq"]:
            # For exact match, use match instead of range
            return {"key": timestamp_column_name, "match": {"value": value}}
        else:
            LOGGER.warning(f"Unsupported timestamp operator: {operator}")
            return None

    def _build_query_filter(self, query_filter: str) -> Optional[dict]:
        if not query_filter:
            return None

        # Parse field-value pairs like: field="value" or field=value
        pattern = r'(\w+)\s*([=!]+)\s*["\']?([^"\']+)["\']?'
        match = re.match(pattern, query_filter.strip())

        if not match:
            LOGGER.warning(f"Invalid query filter format: {query_filter}")
            return None

        field_name, operator, value = match.groups()
        value = value.strip()

        # Convert operators to Qdrant match operators
        if operator in ["=", "=="]:
            return {"key": field_name, "match": {"value": value}}
        elif operator in ["!=", "<>"]:
            return {"must_not": [{"key": field_name, "match": {"value": value}}]}
        else:
            LOGGER.warning(f"Unsupported query operator: {operator}")
            return None

    def _combine_filters(
        self,
        base_filter: Optional[dict],
        additional_filters: list[dict],
    ) -> Optional[dict]:
        valid_filters = [f for f in additional_filters if f is not None]

        # If no filters at all, return None
        if not valid_filters and not base_filter:
            return None

        # If only base filter, ensure it's properly structured
        if not valid_filters:
            if base_filter:
                # Check if it's already properly structured
                if "must" in base_filter or "must_not" in base_filter:
                    return base_filter
                else:
                    # Wrap bare condition in proper structure
                    return {"must": [base_filter]}
            return None

        # If only additional filters and no base filter
        if not base_filter:
            if len(valid_filters) == 1:
                single_filter = valid_filters[0]
                # Check if it's already properly structured
                if "must" in single_filter or "must_not" in single_filter:
                    return single_filter
                else:
                    # Wrap bare condition in proper structure
                    return {"must": [single_filter]}
            # Multiple additional filters will be handled below

        # Collect all conditions that need to be combined
        must_conditions = []
        must_not_conditions = []

        # Process base filter
        if base_filter:
            # Handle string filters (convert them to proper query filters)
            if isinstance(base_filter, str):
                parsed_base = self._build_query_filter(base_filter)
                if parsed_base:
                    if "must" in parsed_base:
                        must_conditions.extend(parsed_base["must"])
                    elif "must_not" in parsed_base:
                        must_not_conditions.extend(parsed_base["must_not"])
                    else:
                        must_conditions.append(parsed_base)
            elif isinstance(base_filter, dict):
                if "must" in base_filter:
                    must_conditions.extend(base_filter["must"])
                elif "must_not" in base_filter:
                    must_not_conditions.extend(base_filter["must_not"])
                else:
                    # Base filter is a single condition
                    must_conditions.append(base_filter)

        # Process additional filters
        for filter_dict in valid_filters:
            # Skip string filters that weren't properly parsed
            if isinstance(filter_dict, str):
                LOGGER.warning(f"Skipping unparsed string filter: {filter_dict}")
                continue

            if isinstance(filter_dict, dict):
                if "must" in filter_dict:
                    must_conditions.extend(filter_dict["must"])
                elif "must_not" in filter_dict:
                    must_not_conditions.extend(filter_dict["must_not"])
                else:
                    # Single condition filter
                    must_conditions.append(filter_dict)

        # Build the combined filter - always use proper Qdrant structure
        combined_filter = {}
        if must_conditions:
            combined_filter["must"] = must_conditions
        if must_not_conditions:
            combined_filter["must_not"] = must_not_conditions

        return combined_filter if combined_filter else None

    def _build_combined_filter(
        self,
        base_filter: Optional[dict] = None,
        query_filter: Optional[str] = None,
        timestamp_filter: Optional[str] = None,
        timestamp_column_name: Optional[str] = None,
    ) -> Optional[dict]:
        additional_filters = []

        if query_filter:
            query_dict = self._build_query_filter(query_filter)
            if query_dict:
                additional_filters.append(query_dict)

        if timestamp_filter and timestamp_column_name:
            timestamp_dict = self._build_timestamp_filter(timestamp_filter, timestamp_column_name)
            if timestamp_dict:
                additional_filters.append(timestamp_dict)

        return self._combine_filters(base_filter, additional_filters)

    def get_points(
        self,
        collection_name: str,
        filter: Optional[dict] = None,
        with_payload: Union[bool, dict] = True,
    ) -> list[dict]:
        return asyncio.run(self.get_points_async(collection_name, filter, with_payload))

    async def get_points_async(
        self,
        collection_name: str,
        filter: Optional[dict] = None,
        with_payload: Union[bool, dict] = True,
        batch_size: int = 50,
    ) -> list[dict]:
        all_points: list[dict] = []
        offset = None
        while True:
            request_body: dict[str, Any] = {
                "limit": batch_size,
                "with_payload": with_payload,
                "with_vector": False,
            }
            if offset is not None:
                request_body["offset"] = offset
            if filter:
                request_body["filter"] = filter
            response = await self._send_request_async(
                method="POST",
                endpoint=f"collections/{collection_name}/points/scroll?wait=true",
                payload=request_body,
            )
            result = response.get("result", {})
            points = result.get("points", [])
            all_points.extend(points)
            offset = result.get("next_page_offset")
            if not offset or not points:
                break
        return all_points

    def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists in Qdrant.

        Args:
            collection_name (str): The name of the collection to check.
        Returns:
            bool: True if the collection exists, False otherwise.
        """
        return asyncio.run(self.collection_exists_async(collection_name))

    async def collection_exists_async(self, collection_name: str) -> bool:
        """Async version of collection_exists."""
        response = await self._send_request_async(method="GET", endpoint=f"collections/{collection_name}/exists")
        return response.get("result", {}).get("exists", False)

    async def get_collection_info_async(self, collection_name: str) -> dict:
        """Return the full collection info payload from Qdrant."""
        response = await self._send_request_async(method="GET", endpoint=f"collections/{collection_name}")
        return response.get("result", {})

    async def is_hybrid_collection_async(self, collection_name: str) -> bool:
        """Check whether a collection has both dense and sparse named vectors."""
        info = await self.get_collection_info_async(collection_name)
        sparse_vectors = info.get("config", {}).get("params", {}).get("sparse_vectors", {})
        return bool(sparse_vectors and "sparse" in sparse_vectors)

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 3072,
        distance: str = "Cosine",
    ) -> bool:
        """
        Create a new collection in Qdrant.

        Args:
            collection_name (str): The name of the collection to create.
            vector_size (int): The size of the vectors to store in the collection.
            distance (str): The distance metric to use for the collection.
        Returns:
            message (str): The status of the operation.
        """
        return asyncio.run(self.create_collection_async(collection_name, vector_size, distance))

    async def create_collection_async(
        self,
        collection_name: str,
        vector_size: int = 3072,
        distance: str = "Cosine",
        schema: Optional[QdrantCollectionSchema] = None,
    ) -> bool:
        """Async version of create_collection."""
        if self._embedding_service is None:
            # TODO : suppress vector size from the method and clean the code
            embedding_size = vector_size
        else:
            embedding_size = self._embedding_service.embedding_size
        if not schema:
            schema = self.default_schema
        if await self.collection_exists_async(collection_name):
            LOGGER.error(f"Collection {collection_name} already exists.")
            return False

        payload = {
            "vectors": {"dense": {"size": embedding_size, "distance": distance}},
            "sparse_vectors": {"sparse": {"modifier": "idf"}},
        }

        response = await self._send_request_async(
            method="PUT", endpoint=f"collections/{collection_name}?wait=true", payload=payload
        )
        if "result" in response:
            LOGGER.info(f"Status of collection creation {collection_name} : {response['result']}")
            # TODO: Remove when production qdrant collections have proper indexes
            await self._create_indexes_from_schema(collection_name=collection_name, schema=schema)
            return True
        LOGGER.error(f"Problem with status of collection creation {collection_name} : {response}")
        return False

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection in Qdrant.

        Args:
            collection_name (str): The name of the collection to delete.
        Returns:
            message (str): The status of the operation.
        """
        return asyncio.run(self.delete_collection_async(collection_name))

    async def delete_collection_async(self, collection_name: str) -> bool:
        """Async version of delete_collection."""
        response = await self._send_request_async(method="DELETE", endpoint=f"collections/{collection_name}?wait=true")
        if "result" in response:
            LOGGER.info(f"Status of collection deletion {collection_name} : {response['result']}")
            return True
        LOGGER.error(f"Problem with status of collection deletion {collection_name} : {response}")
        return False

    def count_points(
        self,
        collection_name: str,
        filter: Optional[dict] = None,
    ) -> int:
        return asyncio.run(self.count_points_async(collection_name, filter))

    async def count_points_async(
        self,
        collection_name: str,
        filter: Optional[dict] = None,
    ) -> int:
        if not await self.collection_exists_async(collection_name):
            raise ValueError(f"Collection {collection_name} does not exist.")

        payload = {"filter": filter} if filter else {}

        LOGGER.info(f"Counting points in collection {collection_name} with filter {filter}")

        response = await self._send_request_async(
            method="POST", endpoint=f"collections/{collection_name}/points/count", payload=payload
        )
        return response.get("result", {}).get("count", 0)

    def delete_points(
        self,
        collection_name: str,
        point_ids: Optional[list[str]] = None,
        filter: Optional[dict] = None,
    ) -> bool:
        return asyncio.run(self.delete_points_async(collection_name, point_ids, filter))

    async def delete_points_async(
        self,
        collection_name: str,
        point_ids: Optional[list[str]] = None,
        filter: Optional[dict] = None,
    ) -> bool:
        """
        Async version of delete_points.
        Either point_ids or filter must be provided, but not both.
        """
        if filter and point_ids:
            LOGGER.error("Cannot provide both point_ids and filter. Please provide only one.")
            return False

        if filter:
            payload = {"filter": filter}
        elif point_ids:
            payload = {"points": point_ids}
        else:
            LOGGER.error("Either point_ids or filter must be provided")
            return False

        response = await self._send_request_async(
            method="POST", endpoint=f"collections/{collection_name}/points/delete?wait=true", payload=payload
        )
        if "result" in response:
            deletion_type = "by filter" if filter else "by IDs"
            LOGGER.info(f"Status of points deletion {deletion_type}: {response['result']}")
            return True
        LOGGER.error(f"Problem with status of points deletion: {response}")
        return False

    def insert_points_in_collection(
        self,
        points: list[dict],
        collection_name: str,
    ) -> bool:
        """
        Put points in the Qdrant collection.

        Args:
            points (list[dict]): A list of points to put in the collection.
            The format of one dict should be the following:
                {"id": 1 (int or uuuid),
                "payload": {"color": "red"},
                "vector": [0.9, 0.1, 0.1] (list of float)
                }
        Returns:
            str: The status of the operation.
        """
        return asyncio.run(self.insert_points_in_collection_async(points, collection_name))

    async def insert_points_in_collection_async(
        self,
        points: list[dict],
        collection_name: str,
    ) -> bool:
        """
        Async version of insert_points_in_collection.
        Put points in the Qdrant collection.
        """
        payload = {"points": points}
        response = await self._send_request_async(
            method="PUT", endpoint=f"collections/{collection_name}/points?wait=true", payload=payload
        )
        if "result" in response:
            LOGGER.info(f"Status of points addition : {response['result']}")
            return True
        LOGGER.error(f"Problem with status of points addition : {response}")
        return False

    def list_collection_names(self) -> list[str]:
        """
        Retrieve a list of all collection names in Qdrant.

        Returns:
            list[str]: A list of collection names.
        """
        return asyncio.run(self.list_collection_names_async())

    async def list_collection_names_async(self) -> list[str]:
        """
        Async version of list_collection_names.
        Retrieve a list of all collection names in Qdrant.
        """
        response = await self._send_request_async(method="GET", endpoint="collections")
        collections = response.get("result", {}).get("collections", [])
        return [collection["name"] for collection in collections]

    async def sync_batched_with_collection_async(
        self,
        incoming_ids_with_timestamp: dict[str, Optional[str]],
        fetch_rows: Callable[[list[str]], list[dict]],
        collection_name: str,
        query_filter_qdrant: Optional[dict] = None,
        batch_size: int = 50,
    ) -> bool:
        """Diff-based sync that fetches full rows only for chunks that need insert/update.

        Phase 1: diff incoming IDs+timestamps against Qdrant existing IDs+timestamps.
        Phase 2: delete stale chunks.
        Phase 3: fetch full rows via fetch_rows in batches and insert them.
        """
        schema = self._get_schema(collection_name)
        chunk_id_field = schema.chunk_id_field
        timestamp_field = schema.last_edited_ts_field

        collection_count = await self.count_points_async(
            collection_name=collection_name,
            filter=query_filter_qdrant,
        )
        LOGGER.info(
            f"Qdrant sync diff: {len(incoming_ids_with_timestamp)} incoming, "
            f"{collection_count} existing in Qdrant (filter={query_filter_qdrant})"
        )
        if collection_count == 0:
            LOGGER.info("Qdrant collection empty for filter — uploading all chunks")
            ids_to_upsert = set(incoming_ids_with_timestamp.keys())
        else:
            fields = [chunk_id_field] + ([timestamp_field] if timestamp_field else [])
            points = await self.get_points_async(
                collection_name=collection_name,
                filter=query_filter_qdrant,
                with_payload={"include": fields},
            )
            existing_ids_with_timestamp: dict[str, Optional[str]] = {
                point["payload"][chunk_id_field]: point["payload"].get(timestamp_field) if timestamp_field else None
                for point in points
                if chunk_id_field in point.get("payload", {})
            }

            ids_to_add = incoming_ids_with_timestamp.keys() - existing_ids_with_timestamp.keys()
            ids_to_delete = existing_ids_with_timestamp.keys() - incoming_ids_with_timestamp.keys()
            common_ids = incoming_ids_with_timestamp.keys() & existing_ids_with_timestamp.keys()

            if not timestamp_field:
                ids_to_update = common_ids
            else:
                ids_to_update = {
                    chunk_id
                    for chunk_id in common_ids
                    if self._should_update(
                        incoming_ids_with_timestamp[chunk_id],
                        existing_ids_with_timestamp[chunk_id],
                    )
                }
            LOGGER.info(
                f"Qdrant sync diff result: {len(ids_to_add)} to add, "
                f"{len(ids_to_update)} to update, {len(ids_to_delete)} to delete, "
                f"{len(common_ids) - len(ids_to_update)} unchanged"
            )

            ids_to_delete = ids_to_delete | ids_to_update
            ids_to_upsert = ids_to_add | ids_to_update

            if ids_to_delete:
                await self.delete_chunks_async(
                    point_ids=list(ids_to_delete),
                    id_field=chunk_id_field,
                    collection_name=collection_name,
                    filter=query_filter_qdrant,
                )
                LOGGER.info(f"Deleted {len(ids_to_delete)} chunks from Qdrant")

        if ids_to_upsert:
            upsert_list = list(ids_to_upsert)
            for i in range(0, len(upsert_list), batch_size):
                batch_ids = upsert_list[i : i + batch_size]
                batch_rows = fetch_rows(batch_ids)
                if not batch_rows:
                    LOGGER.warning(f"Batch {i // batch_size + 1}: fetch_rows returned 0 rows for {len(batch_ids)} IDs")
                    continue
                success = await self.add_chunks_async(batch_rows, collection_name)
                if not success:
                    LOGGER.error(f"Batch {i // batch_size + 1}: add_chunks_async failed for {len(batch_rows)} rows")
                    return False
                LOGGER.info(f"Inserted batch {i // batch_size + 1} ({len(batch_rows)} rows) to Qdrant")

        total_incoming = len(incoming_ids_with_timestamp)
        point_count = await self.count_points_async(
            collection_name=collection_name,
            filter=query_filter_qdrant,
        )
        if point_count != total_incoming:
            LOGGER.error(
                f"Sync failed : number of points in Qdrant ({point_count}) is not equal to "
                f"the number of incoming rows ({total_incoming})"
            )
            return False
        LOGGER.info(f"Sync successful : number of points in Qdrant is {point_count}")
        return True
