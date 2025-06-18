import pandas as pd
from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import TermDefinition
from engine.trace.trace_manager import TraceManager
from engine.agent.utils import fuzzy_matching

NUMBER_CHUNKS_TO_DISPLAY_TRACE = 30


class VocabularySearch:
    def __init__(
        self,
        trace_manager: TraceManager,
        vocabulary_context_data: dict,
        fuzzy_threshold: int = 90,
        fuzzy_matching_candidates: int = 10,
        vocabulary_context_prompt_key: str = "retrieved_definitions",
        component_instance_name: str = "Vocabulary Search",
        term_column: str = "term",
        definition_column: str = "definition",
    ):
        self.trace_manager = trace_manager
        self.component_instance_name = component_instance_name
        self.term_column = term_column
        self.definition_column = definition_column
        self.fuzzy_threshold = fuzzy_threshold
        self.fuzzy_matching_candidates = fuzzy_matching_candidates
        self.vocabulary_context_data = vocabulary_context_data
        self.vocabulary_information: dict[str, TermDefinition] = self._init_vocabulary_information()
        self.vocabulary_context_prompt_key = vocabulary_context_prompt_key

    def _init_vocabulary_information(self):
        vocabulary_information = pd.DataFrame(self.vocabulary_context_data)
        map_vocabulary = {
            row[self.term_column].lower(): TermDefinition(
                term=row[self.term_column], definition=row[self.definition_column]
            )
            for _, row in vocabulary_information.iterrows()
        }
        return map_vocabulary

    def _get_chunks_without_trace(
        self,
        query_text: str,
    ) -> list[TermDefinition]:
        matching_vocabulary_chunks = fuzzy_matching(
            query_text.lower(),
            [vocab for vocab in self.vocabulary_information.keys()],
            fuzzy_matching_candidates=self.fuzzy_matching_candidates,
        )
        candidates_vocabulary_chunks = [
            self.vocabulary_information[match[0]]
            for match in matching_vocabulary_chunks
            if match[1] >= self.fuzzy_threshold
        ]
        return candidates_vocabulary_chunks

    def get_chunks(
        self,
        query_text: str,
    ) -> list[TermDefinition]:
        with self.trace_manager.start_span(self.__class__.__name__) as span:
            chunks = self._get_chunks_without_trace(query_text)
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                    SpanAttributes.INPUT_VALUE: query_text,
                }
            )

            if len(chunks) > NUMBER_CHUNKS_TO_DISPLAY_TRACE:
                for i, chunk in enumerate(chunks):
                    span.add_event(
                        f"Retrieved Vocabulary {i}",
                        {
                            "content": chunk.definition,
                            "id": chunk.term,
                        },
                    )
            else:
                # TODO: delete this block when we refactor the trace manager
                for i, chunk in enumerate(chunks):
                    span.set_attributes(
                        {
                            f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": chunk.definition,
                            f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": chunk.term,
                        }
                    )
            span.set_status(trace_api.StatusCode.OK)

        return chunks
