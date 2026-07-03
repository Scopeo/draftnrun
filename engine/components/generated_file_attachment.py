import base64
import logging
from pathlib import Path
from typing import Any, Optional

from engine.components.types import AgentPayload, ChatMessage, ToolDescription
from engine.temps_folder_utils import get_output_dir

LOGGER = logging.getLogger(__name__)
MAX_GENERATED_PDF_BYTES = 10 * 1024 * 1024

ATTACH_GENERATED_FILES_TOOL_NAME = "attach_generated_files_to_llm"
ATTACH_GENERATED_FILES_TOOL_DESCRIPTION = ToolDescription(
    name=ATTACH_GENERATED_FILES_TOOL_NAME,
    description=(
        "Attach generated PDF files to the next LLM call so you can read them directly. "
        "Only use filenames listed in Available generated files."
    ),
    tool_properties={
        "filenames": {
            "type": "array",
            "description": "Generated PDF filenames to attach to the next LLM call.",
            "items": {"type": "string"},
        },
    },
    required_tool_properties=["filenames"],
)


def extract_generated_files_from_artifacts(artifacts: Optional[dict]) -> list[str]:
    if not artifacts:
        return []

    files = artifacts.get("files")
    if not isinstance(files, list):
        return []

    return [filename for filename in files if isinstance(filename, str) and filename]


def extract_attached_generated_files_from_artifacts(artifacts: Optional[dict]) -> list[str]:
    if not artifacts:
        return []

    files = artifacts.get("attached_files")
    if not isinstance(files, list):
        return []

    return [filename for filename in files if isinstance(filename, str) and filename]


def build_generated_pdf_message_parts(attached_files: list[str]) -> list[dict[str, Any]]:
    pdf_files = [filename for filename in attached_files if Path(filename).suffix.lower() == ".pdf"]
    if not pdf_files:
        return []

    try:
        output_dir = get_output_dir()
    except ValueError as e:
        LOGGER.warning(f"Could not attach generated PDF files: {str(e)}")
        return []

    file_parts = []
    for filename in pdf_files:
        if Path(filename).name != filename:
            LOGGER.warning(f"Skipping generated PDF with non-root filename: {filename}")
            continue

        file_path = output_dir / filename
        if not file_path.is_file():
            LOGGER.warning(f"Generated PDF not found in temp folder: {filename}")
            continue

        try:
            file_size = file_path.stat().st_size
            if file_size > MAX_GENERATED_PDF_BYTES:
                LOGGER.warning(
                    f"Skipping generated PDF {filename}: size {file_size} exceeds {MAX_GENERATED_PDF_BYTES} bytes"
                )
                continue

            file_data = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        except OSError as e:
            LOGGER.warning(f"Skipping generated PDF {filename}: could not read file: {str(e)}")
            continue

        file_parts.append({
            "type": "file",
            "file": {
                "filename": filename,
                "file_data": f"data:application/pdf;base64,{file_data}",
            },
        })

    return file_parts


def append_file_parts_to_latest_user_message(
    messages: list[dict[str, Any]],
    file_parts: list[dict[str, Any]],
) -> None:
    if not file_parts:
        return

    for message in reversed(messages):
        if message.get("role") != "user":
            continue

        content = message.get("content") or ""
        if isinstance(content, list):
            message["content"] = [*content, *file_parts]
        else:
            message["content"] = [{"type": "text", "text": str(content)}, *file_parts]
        return

    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": "Attached generated file(s) requested by the previous tool call."},
            *file_parts,
        ],
    })


def mask_file_data_for_trace(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    masked_messages = []
    for message in messages:
        masked_message = dict(message)
        content = masked_message.get("content")
        if isinstance(content, list):
            masked_content = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "file" and isinstance(item.get("file"), dict):
                    masked_item = dict(item)
                    masked_item["file"] = {**item["file"], "file_data": "<generated PDF omitted from trace>"}
                    masked_content.append(masked_item)
                else:
                    masked_content.append(item)
            masked_message["content"] = masked_content
        masked_messages.append(masked_message)
    return masked_messages


def attach_generated_files_tool_output(
    original_agent_inputs: tuple[AgentPayload, ...], filenames: Any
) -> AgentPayload:
    if not isinstance(filenames, list):
        return AgentPayload(
            messages=[ChatMessage(role="assistant", content="filenames must be a list of generated PDF filenames")],
            error="filenames must be a list",
        )

    available_files: set[str] = set()
    for agent_input in original_agent_inputs:
        available_files.update(extract_generated_files_from_artifacts(agent_input.artifacts))

    selected_files = [
        filename
        for filename in filenames
        if isinstance(filename, str)
        and filename in available_files
        and Path(filename).suffix.lower() == ".pdf"
        and Path(filename).name == filename
    ]

    if not selected_files:
        return AgentPayload(
            messages=[
                ChatMessage(
                    role="assistant",
                    content="No generated PDF files were attached. Use exact PDF filenames from artifacts.files.",
                )
            ],
            error="no generated PDF files selected",
        )

    return AgentPayload(
        messages=[
            ChatMessage(
                role="assistant",
                content=f"Attached generated PDF file(s) to the next LLM call: {', '.join(selected_files)}",
            )
        ],
        artifacts={"attached_files": selected_files},
        is_final=False,
    )
