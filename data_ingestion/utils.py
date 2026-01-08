import json
import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Optional

import pandas as pd
import tiktoken
from pydantic import BaseModel, Field

from engine.storage_service.db_service import DBService

IMAGE_DESCRIPTION_INITIAL_PROMPT = (
    "You will be provided with both the text and the image, "
    "as well as the specific location of the image within that section. "
    "Provide a description of the image. \n"
    "The description should contain everything "
    "that is useful to understand the object shown and it should ignore the background. \n"
    "Include only information that is on the image itself, not the text. \n"
    "Here is the text of the section: \n {section}."
)

IMAGE_DESCRIPTION_INTRODUCTION_PROMPT_TEMPLATE = (
    "You are an assistant that aim is to describe images with "
    "the level of detail that is useful to understand the object shown. \n"
    "The input of the task is a full section of a document "
    "that contains some text and an image. \n"
)


class Chunk(BaseModel):
    chunk_id: str
    file_id: str
    order: Optional[int] = None
    content: str
    last_edited_ts: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_dump_with_metadata(self) -> dict[str, Any]:
        """
        Custom serialization method that merges `metadata` into the root dictionary.
        """
        base_dict = self.model_dump(exclude={"metadata"})  # Dump the model without "metadata"
        return {**base_dict, **self.metadata}  # Merge metadata into base dictionary


def get_last_modification_time_from_local_file(file_path: str) -> str:
    modification_time = os.path.getmtime(file_path)
    return datetime.fromtimestamp(modification_time).strftime("%Y-%m-%d %H:%M:%S")


def read_chunk_table(table_name: str, db_service: DBService) -> dict:
    """
    Read the chunk table from the database
    """
    df = db_service.get_table_df(table_name=table_name)
    if "bounding_boxes" in df.columns:
        df["bounding_boxes"] = df["bounding_boxes"].apply(json.loads)
    return df.to_dict(orient="records")


def sanitize_filename(filename, remove_extension_dot=True):
    # Handle None input
    if filename is None:
        return ""

    # Convert to string if not already
    filename = str(filename)

    # Convert accented characters to non-accented equivalents
    filename = unicodedata.normalize("NFKD", filename).encode("ASCII", "ignore").decode("ASCII")
    # Replace '&' with 'and'
    filename = filename.replace("&", "and")
    # Replace spaces with underscores
    filename = filename.replace(" ", "_")
    # Replace "-" with "_"
    filename = filename.replace("-", "_")
    # Remove any characters that are not alphanumeric, underscores, or dots
    if remove_extension_dot:
        filename = filename.replace(".", "_")
        filename = re.sub(r"[^a-zA-Z0-9_]", "", filename)
    else:
        filename = re.sub(r"[^a-zA-Z0-9_.]", "", filename)
    filename = filename.lower()
    return filename


def get_image_description_prompt(
    section: str, image_description_intro_prompt: str = IMAGE_DESCRIPTION_INTRODUCTION_PROMPT_TEMPLATE
) -> str:
    PROMPT_TEMPLATE = image_description_intro_prompt + IMAGE_DESCRIPTION_INITIAL_PROMPT
    prompt_template = PROMPT_TEMPLATE.format(section=section)
    return prompt_template


def get_chunk_token_count(
    model_name: str = "gpt-4o-mini",
    chunk_df: pd.DataFrame = None,
) -> int:
    encoding = tiktoken.encoding_for_model(model_name)
    markdown_str = chunk_df.to_markdown(index=False)
    return len(encoding.encode(markdown_str))


def split_df_by_token_limit(
    df: pd.DataFrame,
    max_tokens: int,
) -> list[pd.DataFrame]:
    chunks = []
    current_chunk = []

    for _, row in df.iterrows():
        current_chunk.append(row)
        temp_df = pd.DataFrame(current_chunk, columns=df.columns).reset_index(drop=True)
        if get_chunk_token_count(chunk_df=temp_df) > max_tokens:
            current_chunk.pop()
            chunk_df = pd.DataFrame(current_chunk, columns=df.columns).reset_index(drop=True)
            chunks.append(chunk_df)
            current_chunk = [row]

    if current_chunk:
        chunk_df = pd.DataFrame(current_chunk, columns=df.columns).reset_index(drop=True)
        chunks.append(chunk_df)

    return chunks
