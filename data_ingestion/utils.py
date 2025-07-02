import json
from typing import Any
import os
from datetime import datetime
import re
import unicodedata

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
    content: str
    last_edited_ts: str
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
    # Convert accented characters to non-accented equivalents
    filename = unicodedata.normalize("NFKD", filename).encode("ASCII", "ignore").decode("ASCII")
    # Replace '&' with 'and'
    filename = filename.replace("&", "and")
    # Replace spaces with underscores
    filename = filename.replace(" ", "_")
    # Replace "-" with "_"
    filename = filename.replace("-", "_")
    # Replace "." with "_"
    if remove_extension_dot:
        filename = filename.replace(".", "_")
    # Remove any other special characters
    filename = re.sub(r"[^a-zA-Z0-9_]", "", filename)
    # Make lowercase
    filename = filename.lower()
    return filename


def get_image_description_prompt(
    section: str, image_description_intro_prompt: str = IMAGE_DESCRIPTION_INTRODUCTION_PROMPT_TEMPLATE
) -> str:
    PROMPT_TEMPLATE = image_description_intro_prompt + IMAGE_DESCRIPTION_INITIAL_PROMPT
    prompt_template = PROMPT_TEMPLATE.format(section=section)
    return prompt_template
