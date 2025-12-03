import fitz
import io
import logging
import uuid
from typing import Callable, List, Any, Dict, Optional
from enum import Enum
from pydantic import BaseModel

from engine.llm_services.llm_service import VisionService
from data_ingestion.document.folder_management.folder_management import FileDocument, FileChunk
from data_ingestion.document.prompts_vision_ingestion import (
    PPTX_CONTENT_EXTRACTION_PROMPT,
    PDF_TABLE_OF_CONTENT_EXTRACTION_PROMPT,
    PDF_STRUCTURED_CONTENT_EXTRACTION_PROMPT,
    PDF_CONTENT_EXTRACTION_PROMPT,
    PROMPT_DETERMINE_FILE_TYPE,
)
from data_ingestion.markdown.tree_chunker import parse_markdown_to_chunks
from settings import settings

LOGGER = logging.getLogger(__name__)
OPENAI_MODEL_NAME = "gpt-4o"


class TOCSections(BaseModel):
    title: str
    page_number: int
    level: int


class TableOfContent(BaseModel):
    sections: List[TOCSections]


class SectionsTree(BaseModel):
    start_page: int
    ancestors: List[Dict]
    contained_titles: List[str]
    string_toc: Optional[str] = None


class PDFType(Enum):
    landscape = "landscape"
    portrait = "portrait"


class FileType(BaseModel):
    is_native_pdf: bool
    is_converted_from_powerpoint: bool


def _get_pdf_orientation_from_content(pdf_content) -> PDFType:
    doc = fitz.open(stream=pdf_content, filetype="pdf")
    landscape_pages = 0
    portrait_pages = 0

    for page_num, page in enumerate(doc):
        width, height = page.rect.width, page.rect.height
        if width > height:
            landscape_pages += 1
        else:
            portrait_pages += 1

    total_pages = len(doc)
    if landscape_pages > total_pages / 2:
        return PDFType.landscape, total_pages
    elif portrait_pages > total_pages / 2:
        return PDFType.portrait, total_pages
    else:
        raise ValueError("PDF orientation is mixed or cannot be determined.")


def _pdf_to_images(pdf_content, zoom: float = 3.0):
    """
    Convert a PDF to a series of high-quality images and yield them as in-memory image objects.

    Args:
        pdf_path (str): Path to the input PDF file.
        zoom (float): Zoom factor for image quality. Default is 3.0.
    """
    pdf_document = fitz.Document(stream=pdf_content)
    for page_number in range(len(pdf_document)):
        page = pdf_document[page_number]

        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)
        img_byte_arr = io.BytesIO(pix.tobytes("png"))
        img_byte_arr.seek(0)

        yield img_byte_arr.getvalue()


async def _extract_text_from_pages_as_images(
    prompt: str,
    google_llm_service: VisionService,
    openai_llm_service: VisionService,
    response_format: BaseModel = None,
    image_content_list: List[bytes] = None,
) -> Any:
    try:
        extracted_text = await google_llm_service.get_image_description_async(
            image_content_list=image_content_list,
            text_prompt=prompt,
            response_format=response_format,
        )
        if extracted_text is None:
            raise ValueError("Google LLM returned None")
    except Exception as e:
        LOGGER.warning(f"Google LLM failed: {e}. Switching to OpenAI.")
        openai_llm_service._model_name = OPENAI_MODEL_NAME
        extracted_text = await openai_llm_service.get_image_description_async(
            image_content_list=image_content_list,
            text_prompt=prompt,
            response_format=response_format,
        )
        print("OpenAI LLM response:", extracted_text)

    return extracted_text


def _build_section_hierarchy(sections, level=1, ancestors=None) -> List[SectionsTree]:
    if ancestors is None:
        ancestors = []

    sections_tree = []
    same_level_sections = [section for section in sections if section.level == level]

    for i, current in enumerate(same_level_sections):
        is_last = i == len(same_level_sections) - 1
        current_index = sections.index(current)

        if not is_last:
            next_section = same_level_sections[i + 1]
            next_page = next_section.page_number
        else:
            next_section = None
            next_page = sections[-1].page_number + 1

        page_span = next_page - current.page_number

        nested_sections = [
            section
            for i, section in enumerate(sections)
            if i > current_index
            and section.level > level
            and (section.page_number < next_page or (section.page_number == next_page and section.level > level))
        ]

        if page_span > 5 and nested_sections:
            sections_tree.extend(
                _build_section_hierarchy(nested_sections, level + 1, ancestors + [current.model_dump()])
            )
        else:
            end_index = sections.index(next_section) if next_section else len(sections)
            contained_titles = [
                section.title
                for section in sections[current_index:end_index]
                if section.page_number >= current.page_number
            ]

            section_tree = SectionsTree(
                start_page=current.page_number, ancestors=ancestors, contained_titles=contained_titles
            )
            sections_tree.append(section_tree)
    for section_tree in sections_tree:
        section_tree.string_toc = (
            "\n".join(ancestor["title"] for ancestor in section_tree.ancestors)
            + "\n"
            + "\n".join(section_tree.contained_titles)
        )

    return sections_tree


async def _get_markdown_from_sections(
    sections_tree: List[SectionsTree],
    google_llm_service: VisionService,
    openai_llm_service: VisionService,
    images_content_list: List[bytes],
) -> str:
    markdown_output = ""
    for i, section in enumerate(sections_tree):
        section_end = sections_tree[i + 1].start_page if i + 1 < len(sections_tree) else len(images_content_list)
        start_page = max(0, section.start_page - 1)
        end_page = min(len(images_content_list), section_end + 1)

        section_images = images_content_list[start_page:end_page]

        extracted_text = await _extract_text_from_pages_as_images(
            prompt=PDF_STRUCTURED_CONTENT_EXTRACTION_PROMPT.format(
                section_toc=section.string_toc,
                section_pages_info=f"Pages {start_page} to {end_page}",
            ),
            google_llm_service=google_llm_service,
            openai_llm_service=openai_llm_service,
            image_content_list=section_images,
        )
        markdown_output += extracted_text
        markdown_output += "\n\n"
    return markdown_output


def _create_chunks_from_markdown(
    extracted_text: str,
    extracted_table_of_content: TableOfContent,
    document: FileDocument,
) -> list[FileChunk]:
    markdown_chunks = parse_markdown_to_chunks(file_content=extracted_text, file_name=document.file_name)
    page_numbers = set()
    chunks = []
    for i, chunk in enumerate(markdown_chunks):
        for section in extracted_table_of_content.sections:
            if section.title in chunk.content:
                page_numbers.add(section.page_number)
        document.metadata["page_number"] = sorted(list(page_numbers))
        chunk = FileChunk(
            chunk_id=str(uuid.uuid4()),
            document_id=document.file_name,
            order=i,
            content=chunk.content,
            last_edited_ts=document.last_edited_ts,
            document_title=document.file_name,
            bounding_boxes=[],
            url=document.url,
            metadata=document.metadata,
        )
        chunks.append(chunk)
    return chunks


def _create_chunk_from_text(
    document: FileDocument,
    extracted_text: str,
    page_number: int,
    order: int,
) -> FileChunk:
    """Helper function to create a single chunk from extracted text."""
    document.metadata["page_number"] = page_number
    return FileChunk(
        chunk_id=str(uuid.uuid4()),
        document_id=document.file_name,
        order=order,
        content=extracted_text,
        last_edited_ts=document.last_edited_ts,
        document_title=document.file_name,
        bounding_boxes=None,
        url=document.url,
        metadata={"page_number": page_number, **document.metadata},
    )


async def _process_pdf_page_by_page(
    document: FileDocument,
    content_to_process: bytes,
    google_llm_service: VisionService,
    openai_llm_service: VisionService,
    prompt: str,
    zoom: float,
) -> list[FileChunk]:
    """Process PDF pages individually and return chunks."""
    chunks = []
    for i, img_base64 in enumerate(_pdf_to_images(pdf_content=content_to_process, zoom=zoom)):
        extracted_text = await _extract_text_from_pages_as_images(
            prompt=prompt,
            google_llm_service=google_llm_service,
            openai_llm_service=openai_llm_service,
            image_content_list=[img_base64],
        )
        chunk = _create_chunk_from_text(document, extracted_text, i + 1, order=i)
        chunks.append(chunk)
    return chunks


async def _process_pdf_with_table_of_contents(
    document: FileDocument,
    extracted_table_of_content: TableOfContent,
    google_llm_service: VisionService,
    openai_llm_service: VisionService,
    images_content_list: list[bytes],
) -> list[FileChunk]:
    """Process PDF using table of contents structure."""
    section_hierarchy = _build_section_hierarchy(
        sections=extracted_table_of_content.sections,
        level=1,
    )
    markdown = await _get_markdown_from_sections(
        sections_tree=section_hierarchy,
        google_llm_service=google_llm_service,
        openai_llm_service=openai_llm_service,
        images_content_list=images_content_list,
    )
    return _create_chunks_from_markdown(
        extracted_text=markdown,
        extracted_table_of_content=extracted_table_of_content,
        document=document,
    )


async def create_chunks_from_document(
    document: FileDocument,
    get_file_content: Callable[[str], bytes | str],
    google_llm_service: VisionService,
    openai_llm_service: VisionService,
    # TODO: Fix when we handle via frontend
    number_of_pages_to_detect_document_type: int = settings.NUMBER_OF_PAGES_TO_DETECT_DOCUMENT_TYPE,
    zoom: float = settings.PAGE_RESOLUTION_ZOOM,
    **kwargs,
) -> list[FileChunk]:
    content_to_process = get_file_content(document.id)
    pdf_type, total_pages = _get_pdf_orientation_from_content(content_to_process)
    images_content_list = [img_base64 for img_base64 in _pdf_to_images(pdf_content=content_to_process, zoom=zoom)]
    file_type = await _extract_text_from_pages_as_images(
        prompt=PROMPT_DETERMINE_FILE_TYPE,
        google_llm_service=google_llm_service,
        openai_llm_service=openai_llm_service,
        response_format=FileType,
        image_content_list=images_content_list[:number_of_pages_to_detect_document_type],
    )

    # Handle landscape PDFs or PowerPoint conversions
    if pdf_type == PDFType.landscape or file_type.is_converted_from_powerpoint:
        LOGGER.info("Processing PDF in landscape mode...")
        return await _process_pdf_page_by_page(
            document=document,
            content_to_process=content_to_process,
            google_llm_service=google_llm_service,
            openai_llm_service=openai_llm_service,
            prompt=PPTX_CONTENT_EXTRACTION_PROMPT,
            zoom=zoom,
        )

    # Handle portrait native PDFs
    if pdf_type == PDFType.portrait and file_type.is_native_pdf:
        LOGGER.info("Processing PDF in portrait mode...")

        # Skip TOC processing when using custom models (they often hallucinate page numbers)
        if settings.INGESTION_VIA_CUSTOM_MODEL:
            LOGGER.info("Using custom models - skipping TOC processing, using page-by-page processing instead.")
            return await _process_pdf_page_by_page(
                document=document,
                content_to_process=content_to_process,
                google_llm_service=google_llm_service,
                openai_llm_service=openai_llm_service,
                prompt=PDF_CONTENT_EXTRACTION_PROMPT,
                zoom=zoom,
            )

        # Try to extract table of contents (only for non-custom models)
        try:
            extracted_table_of_content = await _extract_text_from_pages_as_images(
                prompt=PDF_TABLE_OF_CONTENT_EXTRACTION_PROMPT,
                google_llm_service=google_llm_service,
                openai_llm_service=openai_llm_service,
                image_content_list=images_content_list,
                response_format=TableOfContent,
            )
        except Exception as e:
            LOGGER.error(f"Error extracting table of content: {e}")
            extracted_table_of_content = TableOfContent(sections=[])

        # Use TOC-based processing if available, otherwise fall back to page-by-page
        if extracted_table_of_content and extracted_table_of_content.sections:
            try:
                return await _process_pdf_with_table_of_contents(
                    document=document,
                    extracted_table_of_content=extracted_table_of_content,
                    google_llm_service=google_llm_service,
                    openai_llm_service=openai_llm_service,
                    images_content_list=images_content_list,
                )
            except Exception as e:
                LOGGER.error(
                    f"Error processing with table of contents: {e}. " "Falling back to page-by-page processing."
                )
        else:
            LOGGER.info("Table of contents is empty. Falling back to page-by-page processing.")

        # Fallback to page-by-page processing
        return await _process_pdf_page_by_page(
            document=document,
            content_to_process=content_to_process,
            google_llm_service=google_llm_service,
            openai_llm_service=openai_llm_service,
            prompt=PDF_CONTENT_EXTRACTION_PROMPT,
            zoom=zoom,
        )

    # Fallback for any other cases
    LOGGER.warning(
        f"Unexpected PDF type combination: {pdf_type}, "
        f"native={file_type.is_native_pdf}, ppt={file_type.is_converted_from_powerpoint}"
    )
    return await _process_pdf_page_by_page(
        document=document,
        content_to_process=content_to_process,
        google_llm_service=google_llm_service,
        openai_llm_service=openai_llm_service,
        prompt=PDF_CONTENT_EXTRACTION_PROMPT,
        zoom=zoom,
    )
