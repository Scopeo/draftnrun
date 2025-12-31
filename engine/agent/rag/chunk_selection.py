from typing import Optional

from pydantic import BaseModel

from engine.agent.build_context import build_context_from_source_chunks
from engine.agent.types import ComponentAttributes, SourceChunk, SourcedResponse
from engine.llm_services.llm_service import LLMService

CHUNK_SELECTION_PROMPT = (
    "You will be given multiple sources of information which will contain image descrptions. "
    "Your task is to select the most relevant text sources that need further review based on the given question."
    "To select relevant text sources, add their numbers to the 'relevant_text_source_numbers' field. \n\n"
    "Here are the available sources: \n{sources}\n\n"
    "Question: {question}"
)


class RelevantChunk(BaseModel):
    relavent_text_source_numbers: list[int]


class RelevantChunkSelector:
    def __init__(
        self,
        llm_service: LLMService,
        prompt_template: str = CHUNK_SELECTION_PROMPT,
        response_format: BaseModel = RelevantChunk,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        self._llm_service = llm_service
        self._prompt_template = prompt_template
        self._response_format = response_format
        self.component_attributes = component_attributes or ComponentAttributes(
            component_instance_name=self.__class__.__name__
        )

    async def get_response(
        self,
        chunks: list[SourceChunk],
        question: str,
    ) -> RelevantChunk:
        sources = build_context_from_source_chunks(
            sources=chunks,
            llm_metadata_keys=chunks[0].metadata.keys() if chunks else [],
        )
        response = await self._llm_service.constrained_complete_with_pydantic_async(
            messages=[
                {
                    "role": "system",
                    "content": self._prompt_template.format(
                        sources=sources,
                        question=question,
                    ),
                },
            ],
            response_format=self._response_format,
        )
        return SourcedResponse(
            response=response.relavent_text_source_numbers,
            source_chunks=chunks,
        )
