import logging
from pathlib import Path
from typing import Optional, Callable
import re
import tempfile

import pypandoc

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from engine.llm_services.llm_service import VisionService
from data_ingestion.document.markdown_ingestion import CHUNK_SIZE, CHUNK_OVERLAP, chunk_markdown
from data_ingestion.utils import get_image_description_prompt

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


def _docx_to_md(file_content: bytes, extract_image: bool = False) -> str:
    """
    Convert DOCX file content (given as bytes) to Markdown using pypandoc.

    Args:
        file_content (bytes): Raw .docx file content.
        extract_image (bool): Whether to extract embedded images to a temp folder.

    Returns:
        str: Markdown content.
    """
    extra_args = []
    if extract_image:
        folder_path = tempfile.mkdtemp()
        extra_args = ["--extract-media", folder_path]

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
        temp_file.write(file_content)
        temp_file.flush()
        temp_file_path = Path(temp_file.name)

        markdown_content = pypandoc.convert_file(str(temp_file_path), "md", extra_args=extra_args)

    return markdown_content


def _docx_to_md_safe_mode(file_content: bytes, extract_image: bool = False) -> Optional[str]:
    """
    Safe mode function to convert DOCX file content (given as bytes) to Markdown.
    If an error occurs, logs the error and returns None.

    Args:
        file_content (bytes): Raw .docx file content.
        extract_image (bool): Whether to extract embedded images to a temp folder.

    Returns:
        Optional[str]: Markdown content if successful, None if an error occurs.
    """
    try:
        markdown_content = _docx_to_md(file_content, extract_image=extract_image)
    except Exception as e:
        LOGGER.error(f"Error converting docx to markdown: {e}")
        return None

    return markdown_content


def get_image_content_from_path(image_path: Path) -> bytes:
    with open(image_path, "rb") as image_file:
        image_content = image_file.read()
    return image_content


def parse_docx_to_md(
    docx_to_process: FileDocument,
    get_file_content_func: Callable[[str], bytes | str],
    include_images_descriptions: bool = False,
    llm_service_images: Optional[VisionService] = None,
) -> str:
    try:
        docx_content = _docx_to_md(
            get_file_content_func(docx_to_process.id),
            extract_image=include_images_descriptions,
        )
    except Exception as e:
        LOGGER.warning(f"Error converting DOCX to markdown: {e}")
        docx_content = _docx_to_md_safe_mode(
            get_file_content_func(docx_to_process.id),
            extract_image=include_images_descriptions,
        )
        if docx_content is None:
            return ""

    if include_images_descriptions and llm_service_images is None:
        LOGGER.warning("No LLM service provided to get image descriptions. Skipping image descriptions.")
    elif include_images_descriptions:
        image_folder_path = Path(docx_to_process.id).parent / Path(docx_to_process.id).stem / "media"
        image_paths = (
            list(Path(image_folder_path).rglob("*.png"))
            + list(Path(image_folder_path).rglob("*.jpg"))
            + list(Path(image_folder_path).rglob("*.jpeg"))
        )

        image_paths_2_sections = extract_sections_around_images(docx_content)
        for image_path in image_paths:
            image_content = get_image_content_from_path(image_path)
            image_description = llm_service_images.get_image_description(
                image_content_list=[image_content],
                text_prompt=get_image_description_prompt(section=image_paths_2_sections[str(image_path)]),
            )

            image_path_str = str(image_path.relative_to(image_folder_path.parent))
            docx_content = re.sub(
                rf"!\[.*?\]\({re.escape(image_path_str)}\)", f"![{image_description}]({image_path_str})", docx_content
            )
    return docx_content


def get_chunks_from_docx(
    docx_to_process: FileDocument,
    get_file_content_func: Callable[[str], bytes | str],
    include_images_descriptions: bool = False,
    llm_service_images: Optional[VisionService] = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[FileChunk]:
    docx_content = parse_docx_to_md(
        docx_to_process, get_file_content_func, include_images_descriptions, llm_service_images
    )
    return chunk_markdown(docx_to_process, docx_content, chunk_size, chunk_overlap)
