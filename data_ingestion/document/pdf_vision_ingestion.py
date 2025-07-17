import fitz
import io
import logging
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


def _extract_text_from_pages_as_images(
    prompt: str,
    google_llm_service: VisionService,
    openai_llm_service: VisionService,
    response_format: BaseModel = None,
    image_content_list: List[bytes] = None,
) -> Any:
    try:
        extracted_text = google_llm_service.get_image_description(
            image_content_list=image_content_list,
            text_prompt=prompt,
            response_format=response_format,
        )
        if extracted_text is None:
            raise ValueError("Google LLM returned None")
    except Exception as e:
        LOGGER.warning(f"Google LLM failed: {e}. Switching to OpenAI.")
        openai_llm_service._model_name = OPENAI_MODEL_NAME
        extracted_text = openai_llm_service.get_image_description(
            image_content_list=image_content_list,
            text_prompt=prompt,
            response_format=response_format,
        )

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


def _get_markdown_from_sections(
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

        extracted_text = _extract_text_from_pages_as_images(
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
) -> FileChunk:
    markdown_chunks = parse_markdown_to_chunks(file_content=extracted_text, file_name=document.file_name)
    page_numbers = set()
    chunks = []
    for i, chunk in enumerate(markdown_chunks):
        for section in extracted_table_of_content.sections:
            if section.title in chunk.content:
                page_numbers.add(section.page_number)
        document.metadata["page_number"] = sorted(list(page_numbers))
        chunk = FileChunk(
            chunk_id=f"{document.file_name}_{i + 1}",
            file_id=document.file_name,
            content=chunk.content,
            last_edited_ts=document.last_edited_ts,
            document_title=document.file_name,
            bounding_boxes=[],
            url=document.url,
            metadata=document.metadata,
        )
        chunks.append(chunk)
    return chunks


def create_chunks_from_document(
    document: FileDocument,
    get_file_content: Callable[[FileDocument], str],
    google_llm_service: VisionService,
    openai_llm_service: VisionService,
    zoom: float = 3.0,
    number_of_pages_to_detect_document_type: int = settings.NUMBER_OF_PAGES_TO_DETECT_DOCUMENT_TYPE,
    **kwargs,
) -> list[FileChunk]:
    chunks = []
    content_to_process = get_file_content(document.id)
    pdf_type, total_pages = _get_pdf_orientation_from_content(content_to_process)
    images_content_list = [img_base64 for img_base64 in _pdf_to_images(pdf_content=content_to_process, zoom=zoom)]
    file_type = _extract_text_from_pages_as_images(
        prompt=PROMPT_DETERMINE_FILE_TYPE,
        google_llm_service=google_llm_service,
        openai_llm_service=openai_llm_service,
        image_content_list=images_content_list[:number_of_pages_to_detect_document_type],
        response_format=FileType,
    )
    if pdf_type == PDFType.landscape or file_type.is_converted_from_powerpoint:
        LOGGER.info("Processing PDF in landscape mode...")
        for i, img_base64 in enumerate(_pdf_to_images(pdf_content=content_to_process, zoom=zoom)):
            document.metadata["page_number"] = i + 1
            extracted_text = _extract_text_from_pages_as_images(
                prompt=PPTX_CONTENT_EXTRACTION_PROMPT,
                google_llm_service=google_llm_service,
                openai_llm_service=openai_llm_service,
                image_content_list=[img_base64],
            )

            chunk = FileChunk(
                chunk_id=f"{document.file_name}_{i + 1}",
                file_id=document.file_name,
                content=extracted_text,
                last_edited_ts=document.last_edited_ts,
                document_title=document.file_name,
                bounding_boxes=[],
                url=document.url,
                metadata=document.metadata,
            )

            chunks.append(chunk)
    elif pdf_type == PDFType.portrait and file_type.is_native_pdf:
        LOGGER.info("Processing PDF in portrait mode...")

        try:
            extracted_table_of_content = _extract_text_from_pages_as_images(
                prompt=PDF_TABLE_OF_CONTENT_EXTRACTION_PROMPT,
                google_llm_service=google_llm_service,
                openai_llm_service=openai_llm_service,
                image_content_list=images_content_list,
                response_format=TableOfContent,
            )
        except Exception as e:
            LOGGER.warning(f"Error extracting table of content: {e}")
            extracted_table_of_content = TableOfContent(sections=[])

        if extracted_table_of_content and extracted_table_of_content.sections != []:
            section_hierarchy = _build_section_hierarchy(
                sections=extracted_table_of_content.sections,
                level=1,
            )
            markdown = _get_markdown_from_sections(
                sections_tree=section_hierarchy,
                google_llm_service=google_llm_service,
                openai_llm_service=openai_llm_service,
                images_content_list=images_content_list,
            )
            chunks = _create_chunks_from_markdown(
                extracted_text=markdown,
                extracted_table_of_content=extracted_table_of_content,
                document=document,
            )
        else:
            for i, img_base64 in enumerate(_pdf_to_images(pdf_content=content_to_process, zoom=zoom)):
                document.metadata["page_number"] = i + 1
                extracted_text = _extract_text_from_pages_as_images(
                    prompt=PDF_CONTENT_EXTRACTION_PROMPT,
                    google_llm_service=google_llm_service,
                    openai_llm_service=openai_llm_service,
                    image_content_list=[img_base64],
                )

                chunk = FileChunk(
                    chunk_id=f"{document.file_name}_{i + 1}",
                    file_id=document.file_name,
                    content=extracted_text,
                    last_edited_ts=document.last_edited_ts,
                    document_title=document.file_name,
                    bounding_boxes=[],
                    url=document.url,
                    metadata=document.metadata,
                )

                chunks.append(chunk)

    return chunks
