from typing import Dict, List, Optional, Union, Literal
from pydantic import BaseModel, RootModel, Field
import dirtyjson

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
    model_config = {"populate_by_name": True}

    name: str
    type: Literal["json_schema"]
    strict: bool = True
    schema_: JsonSchemaModel = Field(..., alias="schema")


# Rebuild models to resolve forward references
PropertyModel.model_rebuild()
DictModel.model_rebuild()
ListModel.model_rebuild()
JsonSchemaModel.model_rebuild()


def format_prompt_with_pydantic_output(prompt: str, pydantic_model: BaseModel) -> str:
    """
    Formats the prompt with the Pydantic model instance in JSON format.
    Useful when using open source llm with failing constrained output models.

    Args:
        prompt (str): The initial prompt text.
        pydantic_model (BaseModel): The Pydantic model instance to be included in the prompt.

    Returns:
        str: The formatted prompt with the Pydantic model instance.
    """
    pydantic_json_instance = build_generic_pydantic_instance_from_pydantic_model(pydantic_model).model_dump_json(
        indent=2
    )
    return prompt + PROMPT_PYDANTIC_FORMAT.format(pydantic_json_instance=pydantic_json_instance)


def search_for_json_object(json_string: str) -> Optional[str]:
    """
    Extracts a JSON object from a string by finding the first '{' and last '}'.

    This function assumes that the first opening brace and last closing brace
    form a valid JSON object. The actual validation is left to dirtyjson.loads()
    in the calling function.

    Args:
        json_string (str): The string to search for JSON objects in.

    Returns:
        Optional[str]: The JSON object string between first '{' and last '}', or None if not found.
    """
    if not json_string:
        return None

    # Find the first opening brace
    start_index = json_string.find("{")
    if start_index == -1:
        return None

    # Find the last closing brace
    end_index = json_string.rfind("}")
    if end_index == -1 or end_index <= start_index:
        return None

    return json_string[start_index : end_index + 1]


def convert_json_str_to_pydantic(json_str: str, pydantic_model: BaseModel) -> BaseModel:
    """
    Converts a JSON string answer to a Pydantic model instance.

    Args:
        json_str (str): The JSON string to convert.
        pydantic_model (BaseModel): The Pydantic model class to convert the JSON to.

    Returns:
        BaseModel: An instance of the Pydantic model with the data from the JSON string.
    """
    try:
        extracted_json = search_for_json_object(json_str)
        json_data = dirtyjson.loads(extracted_json)
        return pydantic_model.model_validate(json_data)
    except Exception as e:
        raise ValueError(f"Issue with loading json format from LLM output: {e}")
