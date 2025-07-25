import logging
from typing import Optional, Any
from dataclasses import dataclass
import uuid
from datetime import datetime

import requests
import httpx
import pandas as pd

from engine.agent.agent import SourceChunk
from engine.llm_services.llm_service import EmbeddingService
from settings import settings

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_CHUNKS = 10
MAX_BATCH_SIZE_FOR_CHUNK_UPLOAD = 50


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
    metadata_fields_to_keep: Optional[set[str]] = None  # To keep compatibility with Juno data

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

    @classmethod
    def from_defaults(
        cls,
        embedding_service: Optional[EmbeddingService] = None,
        default_collection_schema: Optional[QdrantCollectionSchema] = None,
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
        )

    def _send_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict] = None,
        timeout: float = 20.0,
    ) -> dict:
        """
        Send a request to the Qdrant API.

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE).
            endpoint (str): The Qdrant API endpoint (relative to the base URL).
            payload (Optional[dict]): The request payload for POST/PUT methods.

        Returns:
            dict: The JSON response from the API.
        """
        try:
            response = requests.request(
                method=method,
                url=f"{self._base_url}/{endpoint}",
                json=payload,
                headers=self._headers,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as http_err:
            LOGGER.error(f"HTTP error occurred: {http_err}")
            raise
        except Exception as err:
            LOGGER.error(f"An error occurred: {err}")
            raise

    async def _send_request_async(
        self, method: str, endpoint: str, payload: Optional[dict] = None, timeout: float = 20.0
    ) -> dict:
        """
        Send an async request to the Qdrant API.

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE).
            endpoint (str): The Qdrant API endpoint (relative to the base URL).
            payload (Optional[dict]): The request payload for POST/PUT methods.
            timeout (float): Request timeout in seconds.

        Returns:
            dict: The JSON response from the API.
        """
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
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
        if filter is None:
            filter = {}

        payload = {
            "vector": query_vector,
            "filter": filter,
            "with_payload": True,
            "with_vector": False,
            **search_params,
        }
        response = self._send_request(
            method="POST",
            endpoint=f"collections/{collection_name}/points/search",
            payload=payload,
        )
        vector_results = [(result["id"], result["score"], result["payload"]) for result in response.get("result", [])]
        return vector_results

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
        """
        if filter is None:
            filter = {}

        payload = {
            "vector": query_vector,
            "filter": filter,
            "with_payload": True,
            "with_vector": False,
            **search_params,
        }
        response = await self._send_request_async(
            method="POST",
            endpoint=f"collections/{collection_name}/points/search",
            payload=payload,
        )
        vector_results = [(result["id"], result["score"], result["payload"]) for result in response.get("result", [])]
        return vector_results

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
        if not vector_ids:
            raise ValueError("The list of point IDs cannot be empty.")

        payload = {
            "ids": vector_ids,
            "with_payload": True,
            "with_vector": False,
        }

        response = self._send_request(
            method="POST",
            endpoint=f"collections/{collection_name}/points",
            payload=payload,
        )

        return response.get("result", [])

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
        input_embeddings = input_text
        if isinstance(input_text, str):
            input_embeddings = [input_text]
        return [data.embedding for data in self._embedding_service.embed_text(input_embeddings)]

    async def _build_vectors_async(self, input_text: str | list[str]) -> list[list[float]]:
        """Asynchronously build embedding vectors for the given text using the embedding service."""
        input_embeddings = input_text
        if isinstance(input_text, str):
            input_embeddings = [input_text]
        return [data.embedding for data in await self._embedding_service.embed_text_async(input_embeddings)]

    def apply_date_penalty_to_chunks(
        self,
        vector_results: list[tuple[str, float, dict]],
        metadata_date_key: str,
        default_penalty_rate: float,
        chunk_age_penalty_rate: float,
        max_retrieved_chunks_after_penalty: int,
    ) -> list[tuple[str, float, dict]]:
        ordered_chunks = []
        current_year = datetime.today().year
        start_of_year = datetime(current_year, 1, 1)
        for vector_id, score, payload in vector_results:
            date = payload.get(metadata_date_key)
            if not date:
                penalized_score = default_penalty_rate
            else:
                chunk_date = datetime.strptime(date, "%Y-%m-%d")
                age = max(0, (start_of_year - chunk_date).days / 365)
                penalty = min(age * chunk_age_penalty_rate, 5 * chunk_age_penalty_rate)
                penalized_score = score - penalty
            ordered_chunks.append((vector_id, penalized_score, payload))
        ordered_chunks.sort(key=lambda x: x[1], reverse=True)
        sorted_chunks = ordered_chunks[:max_retrieved_chunks_after_penalty]
        vector_ids, scores, payloads = zip(*sorted_chunks)
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
        metadata_date_key: Optional[str] = None,
        max_retrieved_chunks_after_penalty: Optional[int] = None,
        **search_params,
    ) -> list[SourceChunk]:
        """
        Search for chunks similar to the given text.
        Additional search parameters can be passed as keyword arguments such as limit, filters, etc.
        """
        schema = self._get_schema(collection_name)
        query_vector = self._build_vectors(query_text)[0]
        vector_results = self.search_vectors(
            query_vector=query_vector,
            collection_name=collection_name,
            filter=filter,
            **search_params,
            limit=limit,
        )
        if not vector_results:
            LOGGER.warning(f"No similar vectors found for query: {query_text}")
            return []
        vector_ids, scores, payloads = zip(*vector_results)

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

        results = self.get_chunk_data_by_id(collection_name=collection_name, vector_ids=vector_ids)

        chunks: list[SourceChunk] = []
        for result in results:
            if not (chunk_data := result.get("payload")):
                continue

            query_text = chunk_data.get(schema.content_field)
            if not query_text:
                LOGGER.warning(f"Missing text for chunk: {chunk_data}")
                continue

            if schema.metadata_fields_to_keep:
                metadata = {key: value for key, value in chunk_data.items() if key in schema.metadata_fields_to_keep}
            else:
                metadata = {}
            chunks.append(
                SourceChunk(
                    name=chunk_data.get(schema.chunk_id_field, ""),
                    document_name=chunk_data.get(schema.file_id_field, ""),
                    content=query_text,
                    url=str(chunk_data.get(schema.url_id_field, "")),
                    metadata=metadata,
                )
            )
        return chunks

    async def retrieve_similar_chunks_async(
        self,
        query_text: str,
        collection_name: str,
        limit: int = DEFAULT_MAX_CHUNKS,
        filter: dict = None,
        enable_date_penalty_for_chunks: bool = False,
        chunk_age_penalty_rate: Optional[float] = None,
        default_penalty_rate: Optional[float] = None,
        metadata_date_key: Optional[str] = None,
        max_retrieved_chunks_after_penalty: Optional[int] = None,
        **search_params,
    ) -> list[SourceChunk]:
        """
        Async version of retrieve_similar_chunks.
        Search for chunks similar to the given text.
        """
        schema = self._get_schema(collection_name)
        query_vector = (await self._build_vectors_async(query_text))[0]
        vector_results = await self.search_vectors_async(
            query_vector=query_vector,
            collection_name=collection_name,
            filter=filter,
            **search_params,
            limit=limit,
        )
        if not vector_results:
            LOGGER.warning(f"No similar vectors found for query: {query_text}")
            return []
        vector_ids, scores, payloads = zip(*vector_results)

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

            query_text = chunk_data.get(schema.content_field)
            if not query_text:
                LOGGER.warning(f"Missing text for chunk: {chunk_data}")
                continue

            if schema.metadata_fields_to_keep:
                metadata = {key: value for key, value in chunk_data.items() if key in schema.metadata_fields_to_keep}
            else:
                metadata = {}
            chunks.append(
                SourceChunk(
                    name=chunk_data.get(schema.chunk_id_field, ""),
                    document_name=chunk_data.get(schema.file_id_field, ""),
                    content=query_text,
                    url=str(chunk_data.get(schema.url_id_field, "")),
                    metadata=metadata,
                )
            )
        return chunks

    def check_index_exists(self, collection_name: str, index_name: str) -> bool:
        results = self._send_request(method="GET", endpoint=f"/collections/{collection_name}")
        payload_schema = results.get("result", {}).get("payload_schema", {})
        return index_name in payload_schema

    async def check_index_exists_async(self, collection_name: str, index_name: str) -> bool:
        """Async version of check_index_exists."""
        results = await self._send_request_async(method="GET", endpoint=f"/collections/{collection_name}")
        payload_schema = results.get("result", {}).get("payload_schema", {})
        return index_name in payload_schema

    def create_index_if_needed(self, collection_name: str, index_name: str) -> None:
        if not self.check_index_exists(collection_name, index_name):
            LOGGER.info(f"Creating index '{index_name}' for collection '{collection_name}'")
            endpoint = f"/collections/{collection_name}/index"
            payload = {"field_name": index_name, "field_schema": "keyword"}
            self._send_request(method="PUT", endpoint=endpoint, payload=payload)

    async def create_index_if_needed_async(self, collection_name: str, index_name: str) -> None:
        """Async version of create_index_if_needed."""
        if not await self.check_index_exists_async(collection_name, index_name):
            LOGGER.info(f"Creating index '{index_name}' for collection '{collection_name}'")
            endpoint = f"/collections/{collection_name}/index"
            payload = {"field_name": index_name, "field_schema": "keyword"}
            await self._send_request_async(method="PUT", endpoint=endpoint, payload=payload)

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
        schema = self._get_schema(collection_name)
        self.create_index_if_needed(collection_name, index_name=schema.chunk_id_field)
        if schema.metadata_fields_to_keep:
            for metadata_field in schema.metadata_fields_to_keep:
                self.create_index_if_needed(collection_name, index_name=metadata_field)
        for i in range(0, len(list_chunks), self._max_chunks_to_add):
            current_chunk_batch = list_chunks[i : i + self._max_chunks_to_add]
            list_embeddings = self._build_vectors([chunk[schema.content_field] for chunk in current_chunk_batch])
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
            list_payloads = [
                {
                    "id": self.get_uuid(chunk[schema.chunk_id_field]),
                    "payload": {
                        **{field: chunk[field] for field in payload_fields},
                    },
                    "vector": vector,
                }
                for chunk, vector in zip(current_chunk_batch, list_embeddings)
            ]
            if not self.insert_points_in_collection(
                points=list_payloads,
                collection_name=collection_name,
            ):
                LOGGER.error(f"Failed to add chunks {i} to {i + self._max_chunks_to_add}")
                return False
        LOGGER.info(f"Added {len(list_chunks)} chunks to the collection")
        return True

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
        await self.create_index_if_needed_async(collection_name, index_name=schema.chunk_id_field)
        if schema.metadata_fields_to_keep:
            for metadata_field in schema.metadata_fields_to_keep:
                await self.create_index_if_needed_async(collection_name, index_name=metadata_field)
        for i in range(0, len(list_chunks), self._max_chunks_to_add):
            current_chunk_batch = list_chunks[i : i + self._max_chunks_to_add]
            list_embeddings = await self._build_vectors_async(
                [chunk[schema.content_field] for chunk in current_chunk_batch]
            )
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
            list_payloads = [
                {
                    "id": self.get_uuid(chunk[schema.chunk_id_field]),
                    "payload": {
                        **{field: chunk[field] for field in payload_fields},
                    },
                    "vector": vector,
                }
                for chunk, vector in zip(current_chunk_batch, list_embeddings)
            ]
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
    ) -> bool:
        """Delete chunks from the Qdrant collection based on the list
        of IDs for a given field name."""
        filter_on_qdrant_field = {"should": [{"key": id_field, "match": {"any": point_ids}}]}
        points = self.get_points(filter=filter_on_qdrant_field, collection_name=collection_name)
        return self.delete_points(
            point_ids=[point["id"] for point in points],
            collection_name=collection_name,
        )

    async def delete_chunks_async(
        self,
        point_ids: list[str],
        id_field: str,
        collection_name: str,
    ) -> bool:
        """
        Async version of delete_chunks.
        Delete chunks from the Qdrant collection based on the list
        of IDs for a given field name.
        """
        filter_on_qdrant_field = {"should": [{"key": id_field, "match": {"any": point_ids}}]}
        points = await self.get_points_async(filter=filter_on_qdrant_field, collection_name=collection_name)
        return await self.delete_points_async(
            point_ids=[point["id"] for point in points],
            collection_name=collection_name,
        )

    @staticmethod
    def get_uuid(string_id: str) -> str:
        """Generate a UUID."""
        namespace = uuid.NAMESPACE_DNS
        return str(uuid.uuid5(namespace, string_id))

    def get_points(
        self,
        collection_name: str,
        filter: Optional[dict] = None,
    ) -> list[dict]:
        """
        Search for vectors in the Qdrant collection using a filter.
        Refer to the Qdrant API documentation for more details:
        https://api.qdrant.tech/api-reference/search/points

        Args:
            filter (Optional[dict]): A filter to apply to the search query.
            Example: if you want the vectors with a field matching in a list of values,
            you can use:
            "filter": {
                    "must": [
                        {
                            "key": "city",
                            "match": {
                            "value": "London"
                            }
                        },
                        {
                            "key": "pib",
                            "match": {
                            "value": 100
                            }
                        }
                    ]
                    }
            must is the equivalent of AND. Every condition must be true.
            Here,
            "filter": {
                    "should": [
                        {
                            "key": "city",
                            "match": {
                            "value": "London"
                            }
                        },
                        {
                            "key": "pib",
                            "match": {
                            "value": 100
                            }
                        }
                    ]
                    }
            should is the equivalent of OR. At least one condition must be true.
            collection_name (str): The name of the collection to search in.

        Returns:
            list[str]: A list of vector IDs from the search results.
        """
        payload = {
            "filter": filter,
            "offset": None,
            "limit": max(self.count_points(filter=filter, collection_name=collection_name), 1),
        }
        response = self._send_request(
            method="POST", endpoint=f"collections/{collection_name}/points/scroll?wait=true", payload=payload
        )
        return response.get("result", {}).get("points", [])

    async def get_points_async(
        self,
        collection_name: str,
        filter: Optional[dict] = None,
    ) -> list[dict]:
        """
        Async version of get_points.
        Search for vectors in the Qdrant collection using a filter.
        """
        payload = {
            "filter": filter,
            "offset": None,
            "limit": max(await self.count_points_async(filter=filter, collection_name=collection_name), 1),
        }
        response = await self._send_request_async(
            method="POST", endpoint=f"collections/{collection_name}/points/scroll?wait=true", payload=payload
        )
        return response.get("result", {}).get("points", [])

    def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists in Qdrant.

        Args:
            collection_name (str): The name of the collection to check.
        Returns:
            bool: True if the collection exists, False otherwise.
        """
        response = self._send_request(method="GET", endpoint=f"collections/{collection_name}/exists")
        return response.get("result", {}).get("exists", False)

    async def collection_exists_async(self, collection_name: str) -> bool:
        """Async version of collection_exists."""
        response = await self._send_request_async(method="GET", endpoint=f"collections/{collection_name}/exists")
        return response.get("result", {}).get("exists", False)

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
        if self.collection_exists(collection_name):
            LOGGER.error(f"Collection {collection_name} already exists.")
            return False
        payload = {"vectors": {"size": vector_size, "distance": distance}}
        response = self._send_request(
            method="PUT", endpoint=f"collections/{collection_name}?wait=true", payload=payload
        )
        if "result" in response:
            LOGGER.info(f"Status of collection creation {collection_name} : {response['result']}")
            return True
        LOGGER.error(f"Problem with status of collection creation {collection_name} : {response}")
        return False

    async def create_collection_async(
        self,
        collection_name: str,
        vector_size: int = 3072,
        distance: str = "Cosine",
    ) -> bool:
        """Async version of create_collection."""
        if await self.collection_exists_async(collection_name):
            LOGGER.error(f"Collection {collection_name} already exists.")
            return False
        payload = {"vectors": {"size": vector_size, "distance": distance}}
        response = await self._send_request_async(
            method="PUT", endpoint=f"collections/{collection_name}?wait=true", payload=payload
        )
        if "result" in response:
            LOGGER.info(f"Status of collection creation {collection_name} : {response['result']}")
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
        response = self._send_request(method="DELETE", endpoint=f"collections/{collection_name}?wait=true")
        if "result" in response:
            LOGGER.info(f"Status of collection deletion {collection_name} : {response['result']}")
            return True
        LOGGER.error(f"Problem with status of collection deletion {collection_name} : {response}")
        return False

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
        """
        Count the number of points in the Qdrant collection.

        Args:
            collection_name (str): The name of the collection to count points in.
            filter (Optional[dict]): A filter to apply to the points (optional).

        Returns:
            int: The number of points in the collection.
        """
        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection {collection_name} does not exist.")
        payload = {"filter": filter} if filter else {}
        response = self._send_request(
            method="POST", endpoint=f"collections/{collection_name}/points/count", payload=payload
        )
        return response.get("result", {}).get("count", 0)

    async def count_points_async(
        self,
        collection_name: str,
        filter: Optional[dict] = None,
    ) -> int:
        """Async version of count_points."""
        if not await self.collection_exists_async(collection_name):
            raise ValueError(f"Collection {collection_name} does not exist.")
        payload = {"filter": filter} if filter else {}
        response = await self._send_request_async(
            method="POST", endpoint=f"collections/{collection_name}/points/count", payload=payload
        )
        return response.get("result", {}).get("count", 0)

    def delete_points(
        self,
        point_ids: list[str],
        collection_name: str,
    ) -> bool:
        """
        Delete points from the Qdrant collection.

        Args:
            point_ids (list[str]): A list of point IDs to delete from the collection.
            collection_name (str): The name of the collection to delete points from.

        Returns:
            int: The number of points in the collection.
        """

        payload = {"points": point_ids}
        if not point_ids:
            LOGGER.error("No points provided")
            return False
        response = self._send_request(
            method="POST", endpoint=f"collections/{collection_name}/points/delete?wait=true", payload=payload
        )
        if "result" in response:
            LOGGER.info(f"Status of points deletion : {response['result']}")
            return True
        LOGGER.error(f"Problem with status of points deletion : {response}")
        return False

    async def delete_points_async(
        self,
        point_ids: list[str],
        collection_name: str,
    ) -> bool:
        """Async version of delete_points."""
        payload = {"points": point_ids}
        if not point_ids:
            LOGGER.error("No points provided")
            return False
        response = await self._send_request_async(
            method="POST", endpoint=f"collections/{collection_name}/points/delete?wait=true", payload=payload
        )
        if "result" in response:
            LOGGER.info(f"Status of points deletion : {response['result']}")
            return True
        LOGGER.error(f"Problem with status of points deletion : {response}")
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
        payload = {"points": points}
        response = self._send_request(
            method="PUT", endpoint=f"collections/{collection_name}/points?wait=true", payload=payload
        )
        if "result" in response:
            LOGGER.info(f"Status of points addition : {response['result']}")
            return True
        LOGGER.error(f"Problem with status of points addition : {response}")
        return False

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
        response = self._send_request(method="GET", endpoint="collections")
        collections = response.get("result", {}).get("collections", [])

        return [collection["name"] for collection in collections]

    async def list_collection_names_async(self) -> list[str]:
        """
        Async version of list_collection_names.
        Retrieve a list of all collection names in Qdrant.
        """
        response = await self._send_request_async(method="GET", endpoint="collections")
        collections = response.get("result", {}).get("collections", [])
        return [collection["name"] for collection in collections]

    def get_collection_data(self, collection_name: str) -> pd.DataFrame:
        """
        Retrieve all data for a specific collection, organizing metadata into custom columns.

        Args:
            collection_name (str): The name of the collection to retrieve data for.

        Returns:
            pd.DataFrame: A DataFrame with all points and metadata in the collection.
        """
        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection {collection_name} does not exist.")

        schema = self._get_schema(collection_name)
        all_points = self.get_points(collection_name=collection_name)

        rows = []
        for point in all_points:
            payload = point.get("payload", {})
            row = {
                schema.chunk_id_field: payload.get(schema.chunk_id_field),
                schema.content_field: payload.get(schema.content_field),
                schema.file_id_field: payload.get(schema.file_id_field),
            }
            if schema.url_id_field:
                row[schema.url_id_field] = payload.get(schema.url_id_field)
            if schema.file_id_field:
                row[schema.file_id_field] = payload.get(schema.file_id_field)
            if schema.last_edited_ts_field:
                row[schema.last_edited_ts_field] = payload.get(schema.last_edited_ts_field)

            # Add custom metadata fields if any
            metadata_fields = schema.metadata_fields_to_keep or payload.keys()
            for field in metadata_fields:
                if field not in row:
                    row[field] = payload.get(field)
            rows.append(row)

        return pd.DataFrame(rows)

    async def get_collection_data_async(self, collection_name: str) -> pd.DataFrame:
        """
        Async version of get_collection_data.
        Retrieve all data for a specific collection, organizing metadata into custom columns.
        """
        if not await self.collection_exists_async(collection_name):
            raise ValueError(f"Collection {collection_name} does not exist.")

        schema = self._get_schema(collection_name)
        all_points = await self.get_points_async(collection_name=collection_name)

        rows = []
        for point in all_points:
            payload = point.get("payload", {})
            row = {
                schema.chunk_id_field: payload.get(schema.chunk_id_field),
                schema.content_field: payload.get(schema.content_field),
                schema.file_id_field: payload.get(schema.file_id_field),
            }
            if schema.url_id_field:
                row[schema.url_id_field] = payload.get(schema.url_id_field)
            if schema.file_id_field:
                row[schema.file_id_field] = payload.get(schema.file_id_field)
            if schema.last_edited_ts_field:
                row[schema.last_edited_ts_field] = payload.get(schema.last_edited_ts_field)

            # Add custom metadata fields if any
            metadata_fields = schema.metadata_fields_to_keep or payload.keys()
            for field in metadata_fields:
                if field not in row:
                    row[field] = payload.get(field)
            rows.append(row)

        return pd.DataFrame(rows)

    def sync_df_with_collection(self, df: pd.DataFrame, collection_name: str) -> bool:
        """
        Synchronize a DataFrame with a Qdrant collection.
        The DataFrame should have the same schema as the Qdrant collection.
        The function will update existing points and add new points to the collection.

        Args:
            df (pd.DataFrame): The DataFrame to synchronize with the collection.
            collection_name (str): The name of the collection to sync with.

        Returns:
            bool: True if the synchronization was successful, False otherwise.
        """
        old_df = self.get_collection_data(collection_name)
        if old_df.empty:
            self.add_chunks(df.to_dict(orient="records"), collection_name)
            LOGGER.info(f"Qdrant collection is empty. Added {len(df)} chunks to Qdrant")
            return True

        incoming_ids = set(df[self.default_schema.chunk_id_field])
        existing_ids = set(old_df[self.default_schema.chunk_id_field])
        ids_to_delete = existing_ids - incoming_ids
        new_ids_to_add = incoming_ids - existing_ids

        # merge the two dataframes to get the dataframes to update
        common_df = df.merge(old_df, on=self.default_schema.chunk_id_field, how="inner")

        if self.default_schema.last_edited_ts_field:
            ids_to_update = set(
                common_df[
                    common_df[self.default_schema.last_edited_ts_field + "_x"]
                    > common_df[self.default_schema.last_edited_ts_field + "_y"]
                ][self.default_schema.chunk_id_field]
            )
        else:
            ids_to_update = set(common_df[self.default_schema.chunk_id_field])

        ids_to_delete = ids_to_delete.union(ids_to_update)
        ids_to_upsert = new_ids_to_add.union(ids_to_update)

        if len(ids_to_delete) > 0:
            self.delete_chunks(
                point_ids=list(ids_to_delete),
                id_field=self.default_schema.chunk_id_field,
                collection_name=collection_name,
            )
            LOGGER.info(f"Deleted {len(ids_to_delete)} chunks from Qdrant")
        if len(ids_to_upsert) > 0:
            chunks_to_upsert = df[df[self.default_schema.chunk_id_field].isin(ids_to_upsert)]
            list_payloads = chunks_to_upsert.to_dict(orient="records")
            self.add_chunks(list_payloads, collection_name)
            LOGGER.info(f"Upserted {len(ids_to_upsert)} chunks to Qdrant")

        n_points = self.count_points(collection_name)
        if n_points != len(df):
            LOGGER.error(
                (
                    f"Sync failed : number of points in Qdrant ({n_points}) is not equal to the "
                    f"number of points in the dataframe ({len(df)})"
                )
            )
            return False
        else:
            LOGGER.info(f"Sync successful : number of points in Qdrant is {n_points}")
            return True

    async def sync_df_with_collection_async(self, df: pd.DataFrame, collection_name: str) -> bool:
        """
        Async version of sync_df_with_collection.
        Synchronize a DataFrame with a Qdrant collection asynchronously.
        """
        old_df = await self.get_collection_data_async(collection_name)
        if old_df.empty:
            await self.add_chunks_async(df.to_dict(orient="records"), collection_name)
            LOGGER.info(f"Qdrant collection is empty. Added {len(df)} chunks to Qdrant")
            return True

        incoming_ids = set(df[self.default_schema.chunk_id_field])
        existing_ids = set(old_df[self.default_schema.chunk_id_field])
        ids_to_delete = existing_ids - incoming_ids
        new_ids_to_add = incoming_ids - existing_ids

        # merge the two dataframes to get the dataframes to update
        common_df = df.merge(old_df, on=self.default_schema.chunk_id_field, how="inner")

        if self.default_schema.last_edited_ts_field:
            ids_to_update = set(
                common_df[
                    common_df[self.default_schema.last_edited_ts_field + "_x"]
                    > common_df[self.default_schema.last_edited_ts_field + "_y"]
                ][self.default_schema.chunk_id_field]
            )
        else:
            ids_to_update = set(common_df[self.default_schema.chunk_id_field])

        ids_to_delete = ids_to_delete.union(ids_to_update)
        ids_to_upsert = new_ids_to_add.union(ids_to_update)

        if len(ids_to_delete) > 0:
            await self.delete_chunks_async(
                point_ids=list(ids_to_delete),
                id_field=self.default_schema.chunk_id_field,
                collection_name=collection_name,
            )
            LOGGER.info(f"Deleted {len(ids_to_delete)} chunks from Qdrant")
        if len(ids_to_upsert) > 0:
            chunks_to_upsert = df[df[self.default_schema.chunk_id_field].isin(ids_to_upsert)]
            list_payloads = chunks_to_upsert.to_dict(orient="records")
            await self.add_chunks_async(list_payloads, collection_name)
            LOGGER.info(f"Upserted {len(ids_to_upsert)} chunks to Qdrant")

        n_points = await self.count_points_async(collection_name)
        if n_points != len(df):
            LOGGER.error(
                (
                    f"Sync failed : number of points in Qdrant ({n_points}) is not equal to the "
                    f"number of points in the dataframe ({len(df)})"
                )
            )
            return False
        else:
            LOGGER.info(f"Sync successful : number of points in Qdrant is {n_points}")
            return True
