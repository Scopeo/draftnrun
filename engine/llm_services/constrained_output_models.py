from typing import Dict, List, Literal, Optional, Union

import dirtyjson
from pydantic import BaseModel, RootModel

from engine.llm_services.utils_pydantic_generator import build_generic_pydantic_instance_from_pydantic_model

PROMPT_PYDANTIC_FORMAT = """
Output in the following JSON format:
{pydantic_json_instance}
"""


# Define a base model as a union of different schema types
class PropertyModel(RootModel[Union["DictModel", "ListModel", "StringModel", "NumberModel", "BooleanModel"]]):
    pass


class DictModel(BaseModel):
    type: Union[Literal["object"], List[Literal["object", "null"]]]
    properties: Dict[str, "PropertyModel"]
    description: Optional[str] = None
    required: List[str] = []
    additionalProperties: bool = False


class ListModel(BaseModel):
    type: Union[Literal["array"], List[Literal["array", "null"]]]
    items: "PropertyModel"
    description: Optional[str] = None


class StringModel(BaseModel):
    type: Union[Literal["string"], List[Literal["string", "null"]]]
    description: Optional[str] = None
    enum: Optional[List[str]] = None


class NumberModel(BaseModel):
    type: Union[Literal["number"], List[Literal["number", "null"]]]
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    description: Optional[str] = None


class BooleanModel(BaseModel):
    type: Union[Literal["boolean"], List[Literal["boolean", "null"]]]
    description: Optional[str] = None


class JsonSchemaModel(BaseModel):
    type: Union[Literal["object"], List[Literal["object", "null"]]]
    properties: Dict[str, "PropertyModel"]
    required: List[str]
    additionalProperties: bool = False


class OutputFormatModel(BaseModel):
    name: str
    type: Literal["json_schema"]
    strict: bool = True
    schema: JsonSchemaModel


# Rebuild models to resolve forward references
PropertyModel.model_rebuild()
DictModel.model_rebuild()
ListModel.model_rebuild()
JsonSchemaModel.model_rebuild()


def format_prompt_with_pydantic_output(prompt: str, pydantic_model: BaseModel) -> str:
    pydantic_json_instance = build_generic_pydantic_instance_from_pydantic_model(pydantic_model).model_dump_json(
        indent=2
    )
    return prompt + PROMPT_PYDANTIC_FORMAT.format(pydantic_json_instance=pydantic_json_instance)


def search_for_json_object(json_string: str) -> Optional[str]:
    if not json_string:
        return None

    cleaned = json_string.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    start_index = cleaned.find("{")
    if start_index == -1:
        return None

    end_index = cleaned.rfind("}")
    if end_index == -1 or end_index <= start_index:
        return None

    return cleaned[start_index : end_index + 1]


# TODO: Use a library instead of this inhouse function
def convert_json_str_to_pydantic(json_str: str, pydantic_model: BaseModel) -> BaseModel:
    try:
        if not json_str or not isinstance(json_str, str):
            raise ValueError(f"Expected non-empty string, got: {type(json_str).__name__}")

        extracted_json = search_for_json_object(json_str)
        if extracted_json is None:
            raise ValueError(f"No JSON object found in response. Response text: {json_str[:200]}")

        json_data = dirtyjson.loads(extracted_json)
        return pydantic_model.model_validate(json_data)
    except Exception as e:
        raise ValueError(f"Issue with loading json format from LLM output: {e}")
