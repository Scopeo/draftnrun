import logging
import re
from pathlib import Path
from typing import Callable, Optional

import pypandoc

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from data_ingestion.document.markdown_ingestion import CHUNK_OVERLAP, CHUNK_SIZE, chunk_markdown
from data_ingestion.utils import content_as_temporary_file_path, get_image_description_prompt
from engine.llm_services.llm_service import VisionService

LOGGER = logging.getLogger(__name__)


def extract_sections_around_images(markdown_text: str) -> dict:
    image_pattern = r"!\[.*?\]\((.*?)(?:\)|$)(?:\{.*?\})?"
    matches = re.finditer(image_pattern, markdown_text, re.DOTALL)

    results = {}
    for match in matches:
        image_path = match.group(1)
        start_pos = match.start()
        end_pos = match.end()
        before = markdown_text[max(0, start_pos - 100) : start_pos]
        after = markdown_text[end_pos : min(len(markdown_text), end_pos + 100)]
        surrounding_text = before + markdown_text[start_pos:end_pos] + after
        results[str(image_path)] = {
            "start_pos": start_pos,
            "end_pos": end_pos,
            "context": surrounding_text,
        }
    return results


def _docx_to_md(file_path: str, extract_image: bool = False) -> Optional[str]:
    try:
        extra_args = []
        if extract_image:
            folder_path = Path(file_path).parent / Path(file_path).stem / "media"
            folder_path.mkdir(parents=True, exist_ok=True)
            extra_args = ["--extract-media", str(folder_path.parent)]

        markdown_content = pypandoc.convert_file(file_path, "md", extra_args=extra_args)
        return markdown_content
    except Exception as e:
        LOGGER.error(f"Error converting docx to markdown: {e}", exc_info=True)
        return None


def get_image_content_from_path(image_path: Path) -> bytes:
    with open(image_path, "rb") as image_file:
        image_content = image_file.read()
    return image_content


async def _parse_docx_with_pandoc(
    file_path: str,
    llm_service_images: Optional[VisionService] = None,
) -> str:
    extract_images = llm_service_images is not None
    docx_content = _docx_to_md(file_path, extract_image=extract_images)

    if docx_content is None:
        LOGGER.warning(f"Failed to convert DOCX at {file_path}, returning empty content")
        return ""

    if llm_service_images is None:
        return docx_content

    image_folder_path = Path(file_path).parent / Path(file_path).stem / "media"
    image_paths = (
        list(image_folder_path.rglob("*.png"))
        + list(image_folder_path.rglob("*.jpg"))
        + list(image_folder_path.rglob("*.jpeg"))
    )

    if not image_paths:
        return docx_content

    image_paths_2_sections = extract_sections_around_images(docx_content)
    for image_path in image_paths:
        try:
            image_content = get_image_content_from_path(image_path)
            image_description = llm_service_images.get_image_description(
                image_content_list=[image_content],
                text_prompt=get_image_description_prompt(section=image_paths_2_sections.get(str(image_path), "")),
            )

            image_path_str = str(image_path.relative_to(image_folder_path.parent))
            docx_content = re.sub(
                rf"!\[.*?\]\({re.escape(image_path_str)}\)", f"![{image_description}]({image_path_str})", docx_content
            )
        except Exception as e:
            LOGGER.warning(f"Error processing image {image_path}: {e}")
            continue

    return docx_content


async def get_chunks_from_docx(
    document: FileDocument,
    get_file_content: Callable[[str], bytes | str],
    docx_parser: Callable[[str], str],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    **kwargs,
) -> list[FileChunk]:
    try:
        content_to_process = get_file_content(document.id)
        with content_as_temporary_file_path(content_to_process, suffix=".docx") as file_path:
            try:
                markdown_text = await docx_parser(file_path, **kwargs)
            except Exception as e:
                LOGGER.error(
                    f"Error parsing DOCX {document.file_name}: {e}",
                    exc_info=True,
                )
                raise Exception(f"Error parsing DOCX {document.file_name}") from e
        return chunk_markdown(
            document_to_process=document,
            content=markdown_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except Exception as e:
        LOGGER.error(f"Error processing DOCX {document.file_name}: {e}", exc_info=True)
        raise Exception(f"Error processing DOCX {document.file_name}") from e
