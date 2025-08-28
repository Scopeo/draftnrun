import logging
from typing import Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import Agent
from engine.agent.types import (
    ChatMessage,
    AgentPayload,
    ComponentAttributes,
    ToolDescription,
)
from engine.agent.rag.reranker import Reranker
from engine.agent.rag.retriever import Retriever
from engine.trace.trace_manager import TraceManager
from engine.agent.synthesizer import Synthesizer
from engine.agent.utils import format_qdrant_filter
from engine.agent.rag.formatter import Formatter
from engine.agent.rag.vocabulary_search import VocabularySearch
from engine.agent.build_context import build_context_from_vocabulary_chunks

LOGGER = logging.getLogger(__name__)

# How we combine multiple filters conditions in Qdrant.
FILTERING_CONDITION_WITH_METADATA_QDRANT = "AND"


class RAG(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        retriever: Retriever,
        synthesizer: Synthesizer,
        component_attributes: Optional[ComponentAttributes] = None,
        reranker: Optional["Reranker"] = None,
        formatter: Optional[Formatter] = None,
        vocabulary_search: Optional[VocabularySearch] = None,
        input_data_field_for_messages_history: str = "messages",
    ) -> None:
        if component_attributes is None:
            component_attributes = ComponentAttributes(component_instance_name=self.__class__.__name__)
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._retriever = retriever
        self._synthesizer = synthesizer
        self._reranker = reranker
        if formatter is None:
            formatter = Formatter(add_sources=False)
        self._formatter = formatter
        self._vocabulary_search = vocabulary_search
        self.input_data_field_for_messages_history = input_data_field_for_messages_history

    async def _run_without_io_trace(
        self,
        *inputs: dict | AgentPayload,
        query_text: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> AgentPayload:
        agent_input = inputs[0]
        if not isinstance(agent_input, AgentPayload):
            # TODO : Will be suppressed when AgentPayload will be suppressed
            agent_input["messages"] = agent_input[self.input_data_field_for_messages_history]
            agent_input = AgentPayload(**agent_input)
        content = query_text or agent_input.last_message.content
        if content is None:
            raise ValueError("No content provided for the RAG tool.")
        chunks = await self._retriever.get_chunks(query_text=content, filters=filters)

        if self._reranker is not None:
            chunks = await self._reranker.rerank(query=content, chunks=chunks)

        vocabulary_context = {}
        if self._vocabulary_search is not None:
            vocabulary_chunks = self._vocabulary_search.get_chunks(query_text=content)
            vocabulary_context = {
                self._vocabulary_search.vocabulary_context_prompt_key: build_context_from_vocabulary_chunks(
                    vocabulary_chunks=vocabulary_chunks
                )
            }

        sourced_response = await self._synthesizer.get_response(
            query_str=content,
            chunks=chunks,
            optional_contexts=vocabulary_context,
        )

        sourced_response = self._formatter.format(sourced_response)

        for i, source in enumerate(chunks):
            self.log_trace(
                {
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": source.content,
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": source.name,
                }
            )

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=sourced_response.response)],
            is_final=sourced_response.is_successful,
            artifacts={"sources": sourced_response.sources},
        )


def format_rag_tool_description() -> ToolDescription:
    return ToolDescription(
        name="RAG",
        description=(
            f"Searches a document database to retrieve relevant information in the "
            f"company's knowledge base."
        ),
        tool_properties={
            "query_text": {
                "type": "string",
                "description": "The search query for the knowledge base.",
            },
            # Qdrant filtering docs: https://qdrant.tech/documentation/concepts/filtering
            "filters": {
                "type": "object",
                "description": (
                    "Qdrant filter object. Use top-level 'must' (AND), 'should' (OR), and/or 'must_not' (NOT) arrays of conditions. "
                    "Each condition targets a payload field or special selector. Supported condition forms include: \n"
                    '- Field match (exact): {"key": "<field>", "match": {"value": <string|number|bool>}}\n'
                    '- Match any (IN): {"key": "<field>", "match": {"any": [<values>]}}\n'
                    '- Range/Datetime range: {"key": "<field>", "range": {"gte": v1, "lte": v2}} (dates as ISO 8601 strings)\n'
                    '- Is null: {"is_null": {"key": "<field>"}}\n'
                    '- Is empty: {"is_empty": {"key": "<field>"}}\n'
                    '- Has id (restrict by point ids): {"has_id": [<id1>, <id2>]}\n'
                    '- Has vector (named vector present): {"has_vector": "<name>"}\n'
                    '- Nested object: {"nested": {"key": "<path>", "filter": {"must": [ ... ]}}} or use dot-path in key.\n'
                    "Examples:\n"
                    "1) AND with NOT and date lower bound:\n"
                    '{\n  "must": [\n    {"key": "department", "match": {"any": ["HR", "Legal"]}},\n    {"key": "last_edited_ts", "range": {"gte": "2024-01-01"}}\n  ],\n  "must_not": [\n    {"key": "archived", "match": {"value": true}}\n  ]\n}\n'
                    "2) OR over tags:\n"
                    '{\n  "should": [\n    {"key": "tags", "match": {"any": ["policy", "gdpr"]}}\n  ]\n}\n'
                    "Ensure field names match payload schema."
                ),
                "properties": {
                    "must": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/condition"},
                    },
                    "should": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/condition"},
                    },
                    "must_not": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/condition"},
                    },
                },
                "$defs": {
                    "scalar": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "number"},
                            {"type": "boolean"},
                        ]
                    },
                    "stringOrNumber": {"oneOf": [{"type": "string"}, {"type": "number"}]},
                    "matchValue": {
                        "type": "object",
                        "required": ["value"],
                        "properties": {"value": {"$ref": "#/$defs/scalar"}},
                        "additionalProperties": False,
                    },
                    "matchAny": {
                        "type": "object",
                        "required": ["any"],
                        "properties": {"any": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/scalar"}}},
                        "additionalProperties": False,
                    },
                    "matchCondition": {
                        "type": "object",
                        "required": ["key", "match"],
                        "properties": {
                            "key": {"type": "string"},
                            "match": {"oneOf": [{"$ref": "#/$defs/matchValue"}, {"$ref": "#/$defs/matchAny"}]},
                        },
                        "additionalProperties": False,
                    },
                    "rangeObject": {
                        "type": "object",
                        "properties": {
                            "gt": {"$ref": "#/$defs/stringOrNumber"},
                            "gte": {"$ref": "#/$defs/stringOrNumber"},
                            "lt": {"$ref": "#/$defs/stringOrNumber"},
                            "lte": {"$ref": "#/$defs/stringOrNumber"},
                        },
                        "minProperties": 1,
                        "additionalProperties": False,
                    },
                    "rangeCondition": {
                        "type": "object",
                        "required": ["key", "range"],
                        "properties": {"key": {"type": "string"}, "range": {"$ref": "#/$defs/rangeObject"}},
                        "additionalProperties": False,
                    },
                    "isNullCondition": {
                        "type": "object",
                        "required": ["is_null"],
                        "properties": {
                            "is_null": {
                                "type": "object",
                                "required": ["key"],
                                "properties": {"key": {"type": "string"}},
                                "additionalProperties": False,
                            }
                        },
                        "additionalProperties": False,
                    },
                    "isEmptyCondition": {
                        "type": "object",
                        "required": ["is_empty"],
                        "properties": {
                            "is_empty": {
                                "type": "object",
                                "required": ["key"],
                                "properties": {"key": {"type": "string"}},
                                "additionalProperties": False,
                            }
                        },
                        "additionalProperties": False,
                    },
                    "hasIdCondition": {
                        "type": "object",
                        "required": ["has_id"],
                        "properties": {
                            "has_id": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
                            }
                        },
                        "additionalProperties": False,
                    },
                    "hasVectorCondition": {
                        "type": "object",
                        "required": ["has_vector"],
                        "properties": {"has_vector": {"type": "string"}},
                        "additionalProperties": False,
                    },
                    "nestedCondition": {
                        "type": "object",
                        "required": ["nested"],
                        "properties": {
                            "nested": {
                                "type": "object",
                                "required": ["key", "filter"],
                                "properties": {
                                    "key": {"type": "string"},
                                    "filter": {
                                        "type": "object",
                                        "properties": {
                                            "must": {"type": "array", "items": {"$ref": "#/$defs/condition"}},
                                            "should": {"type": "array", "items": {"$ref": "#/$defs/condition"}},
                                            "must_not": {"type": "array", "items": {"$ref": "#/$defs/condition"}},
                                        },
                                        "additionalProperties": False,
                                    },
                                },
                                "additionalProperties": False,
                            }
                        },
                        "additionalProperties": False,
                    },
                    "condition": {
                        "oneOf": [
                            {"$ref": "#/$defs/matchCondition"},
                            {"$ref": "#/$defs/rangeCondition"},
                            {"$ref": "#/$defs/isNullCondition"},
                            {"$ref": "#/$defs/isEmptyCondition"},
                            {"$ref": "#/$defs/hasIdCondition"},
                            {"$ref": "#/$defs/hasVectorCondition"},
                            {"$ref": "#/$defs/nestedCondition"},
                        ]
                    },
                },
                "additionalProperties": False,
            },
        },
        required_tool_properties=[],
    )
