import logging
from typing import Optional

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.types import SourceChunk, ComponentAttributes
from engine.trace.trace_manager import TraceManager
from engine.storage_service.db_service import DBService
from engine.agent.utils import fuzzy_matching

NUMBER_DOCS_TO_DISPLAY_TRACE = 30

QUERY_DOCUMENT_CONTENT = "SELECT * FROM {schema_name}.{table_name} WHERE " "{document_name_column} IN ({placeholders})"

LOGGER = logging.getLogger(__name__)


class DocumentSearch:
    def __init__(
        self,
        trace_manager: TraceManager,
        db_service: DBService,
        table_name: str,
        schema_name: str,
        document_name_column: str = "document_name",
        content_document_column: str = "document_content",
        fuzzy_threshold: int = 80,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        self.trace_manager = trace_manager
        self.db_service = db_service
        self.table_name = table_name
        self.schema_name = schema_name
        self.document_name_column = document_name_column
        self.content_document_column = content_document_column
        self.fuzzy_threshold = fuzzy_threshold
        self.component_attributes = component_attributes or ComponentAttributes(
            component_instance_name=self.__class__.__name__
        )

    def get_documents_names(self) -> list[str]:
        query = f"SELECT DISTINCT {self.document_name_column} FROM {self.schema_name}.{self.table_name}"
        df_document = self.db_service._fetch_sql_query_as_dataframe(query)
        return df_document[self.document_name_column].tolist()

    def get_closest_documents_to_queried_documents_name(self, queried_documents):
        correct_documents = []
        list_of_correct_documents = self.get_documents_names()
        for document in queried_documents:
            if document in self.get_documents_names():
                correct_documents.append(document)
            else:
                matching_candidates = fuzzy_matching(document, list_of_correct_documents, fuzzy_matching_candidates=1)[
                    0
                ]
                if matching_candidates[1] >= self.fuzzy_threshold:
                    correct_documents.append(matching_candidates[0])
                else:
                    LOGGER.warning(
                        f"No matching document found for {document}. "
                        f"Closest candidate is {matching_candidates[0]} with "
                        f"{matching_candidates[1]} score"
                    )
        return correct_documents

    def _get_documents_without_trace(
        self,
        documents_name: list[str],
    ) -> list[SourceChunk]:
        placeholders = ", ".join([f"'{doc}'" for doc in documents_name])
        query = QUERY_DOCUMENT_CONTENT.format(
            schema_name=self.schema_name,
            table_name=self.table_name,
            document_name_column=self.document_name_column,
            placeholders=placeholders,
        )
        df_document = self.db_service._fetch_sql_query_as_dataframe(query)
        return [
            SourceChunk(
                name=row[self.document_name_column],
                document_name=row[self.document_name_column],
                content=row[self.content_document_column],
                metadata={},
            )
            for _, row in df_document.iterrows()
        ]

    def get_documents(
        self,
        documents_name: list[str],
    ) -> list[SourceChunk]:
        with self.trace_manager.start_span(self.component_attributes.component_instance_name) as span:
            documents_chunks = self._get_documents_without_trace(documents_name)
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                    SpanAttributes.INPUT_VALUE: documents_name,
                    "component_instance_id": str(self.component_attributes.component_instance_id),
                }
            )

            if len(documents_chunks) > NUMBER_DOCS_TO_DISPLAY_TRACE:
                for i, document in enumerate(documents_chunks):
                    span.add_event(
                        f"Retrieved Document {i}",
                        {
                            "document_name": document.document_name,
                            "content_document": document.content,
                        },
                    )
            else:
                # TODO: delete this block when we refactor the trace manager
                for i, document in enumerate(documents_chunks):
                    span.set_attributes(
                        {
                            f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.term": document.document_name,
                            f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.definition": document.content,
                        }
                    )
            span.set_status(trace_api.StatusCode.OK)

        return documents_chunks
