import re
import logging
from typing import Optional
import json

from engine.agent.data_structures import SourceChunk, SourcedResponse, ComponentAttributes


LOGGER = logging.getLogger(__name__)

CITATION_REGEX = r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]"
CITATION_NUMBER_REGEX = r"\d+"
PAGE_NUMBER_FIELD = "PAGE_NUMBER"
BOUNDING_BOXES_FIELD = "bounding_boxes"
DOCUMENT_ID_FIELD = "document_title"


class Formatter:
    def __init__(
        self,
        add_sources: bool = True,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        self._add_sources = add_sources
        self.component_attributes = component_attributes or ComponentAttributes(
            component_instance_name=self.__class__.__name__
        )

    def format(self, sourced_response: SourcedResponse) -> str:
        if not sourced_response.sources:
            return sourced_response
        sourced_response = self._renumber_sources(
            sourced_response=sourced_response,
        )
        if self._add_sources:
            sourced_response = self._format_response_with_sources(sourced_response=sourced_response)
        return sourced_response

    @staticmethod
    def _format_source(
        source: SourceChunk,
        source_number: Optional[int] = None,
    ) -> str:
        source_number_str = f"[{source_number}]" if source_number else "-"
        document_name = (
            source.metadata[DOCUMENT_ID_FIELD] if DOCUMENT_ID_FIELD in source.metadata else source.document_name
        )
        if BOUNDING_BOXES_FIELD in source.metadata:
            list_pages_numbers = sorted(
                list(set([str(bbox["page"]) for bbox in json.loads(source.metadata["bounding_boxes"])]))
            )
            page_numbers = ",".join(list_pages_numbers)
            document_name = f"{document_name}: pages {page_numbers}"
        url_link = source.url + "|" if len(source.url) > 0 else ""
        citation = f"{source_number_str} <{url_link}{document_name}"
        if PAGE_NUMBER_FIELD in source.metadata:
            citation += f" page {source.metadata[PAGE_NUMBER_FIELD]}"
        citation += ">"
        return citation

    def _format_response_with_sources(
        self,
        sourced_response: SourcedResponse,
    ) -> SourcedResponse:
        if not sourced_response.sources:
            LOGGER.info("No sources retrieved for the agent response.")
            return SourcedResponse(
                response=sourced_response.response,
                sources=[],
                is_successful=sourced_response.is_successful,
            )
        citations = []
        for i, source in enumerate(sourced_response.sources):
            citation = self._format_source(source, i + 1)
            citations.append(citation)
        if not citations:
            return SourcedResponse(
                response=sourced_response.response,
                sources=[],
                is_successful=sourced_response.is_successful,
            )
        answer_with_correct_used_citations_numbers = (
            sourced_response.response + "\nSources:\n" + "\n".join(citations) + "\n"
        )

        return SourcedResponse(
            response=answer_with_correct_used_citations_numbers,
            sources=sourced_response.sources,
            is_successful=sourced_response.is_successful,
        )

    @staticmethod
    def _renumber_sources(
        sourced_response: SourcedResponse,
    ) -> SourcedResponse:

        num_sources = len(sourced_response.sources)
        matches = re.findall(CITATION_REGEX, sourced_response.response)
        citations = [re.findall(CITATION_NUMBER_REGEX, match) for match in matches]
        citations_as_int = [[int(num) for num in citation] for citation in citations]

        citation_mapping: dict[int | str, int] = {}
        i = 1
        for citations_group in citations_as_int:
            for citation_number in citations_group:
                if citation_number > num_sources:
                    LOGGER.warning(
                        f"Source number {citation_number} exceeds the number of sources:" f" {num_sources}",
                    )
                    citation_mapping[citation_number] = ""
                    continue
                if citation_number in citation_mapping:
                    continue
                citation_mapping[citation_number] = i
                i += 1

        def replace_citation(match):
            citation_numbers = [int(num) for num in re.findall(CITATION_NUMBER_REGEX, match.group(0))]
            new_citation = "[" + ",".join(str(citation_mapping[num]) for num in citation_numbers) + "]"
            return new_citation

        new_answer = re.sub(CITATION_REGEX, replace_citation, sourced_response.response)

        citations_mapping_without_empty_number = {k: v for k, v in citation_mapping.items() if v != ""}
        used_citations_in_correct_order = sorted(
            citations_mapping_without_empty_number.keys(),
            key=lambda k: citations_mapping_without_empty_number[k],
        )
        used_sources = [
            sourced_response.sources[citation_number - 1] for citation_number in used_citations_in_correct_order
        ]
        return SourcedResponse(
            response=new_answer,
            sources=used_sources,
            is_successful=sourced_response.is_successful,
        )
