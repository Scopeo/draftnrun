from typing import Dict, List, Optional, Union, Literal, get_args, get_origin
from pydantic import BaseModel, RootModel
import dirtyjson

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


def generate_fake_instance_from_pydantic(model_cls: type[BaseModel]) -> BaseModel:
    def _fake_value(field_type):
        origin = get_origin(field_type) or field_type
        args = get_args(field_type)

        # Simple types
        if origin is bool:
            return False
        elif origin is int:
            return 0
        elif origin is float:
            return 0.0
        elif origin is str:
            return "string"
        elif origin is list:
            # for list[T], generate one element of T
            inner_type = args[0] if args else str
            return [_fake_value(inner_type)]
        elif origin is dict:
            return {"key": "value"}
        elif origin is Union:
            # handle Optional[X] (Union[X, None])
            non_none_args = [arg for arg in args if arg is not type(None)]
            return _fake_value(non_none_args[0]) if non_none_args else None
        elif issubclass(origin, BaseModel):
            # nested model
            return generate_fake_instance_from_pydantic(origin)
        else:
            return None

    # build data dict
    data = {name: _fake_value(field.annotation) for name, field in model_cls.model_fields.items()}

    return model_cls(**data)


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
    pydantic_json_instance = generate_fake_instance_from_pydantic(pydantic_model).model_dump_json(indent=2)
    return prompt + PROMPT_PYDANTIC_FORMAT.format(pydantic_json_instance=pydantic_json_instance)


def search_for_json_object(json_string: str) -> Optional[str]:
    index_start_bracket = -1
    index_end_bracket = -1
    for i, (char, reverse_char) in enumerate(zip(json_string, json_string[::-1])):
        if char == "{" and index_start_bracket == -1:
            index_start_bracket = i
        if reverse_char == "}" and index_end_bracket == -1:
            index_end_bracket = len(json_string) - i - 1
    return json_string[index_start_bracket : index_end_bracket + 1]


def convert_json_answer_to_pydantic(json_answer: str, pydantic_model: BaseModel) -> BaseModel:
    """
    Converts a JSON string answer to a Pydantic model instance.

    Args:
        json_answer (str): The JSON string to convert.
        pydantic_model (BaseModel): The Pydantic model class to convert the JSON to.

    Returns:
        BaseModel: An instance of the Pydantic model with the data from the JSON string.
    """
    try:
        extracted_json = search_for_json_object(json_answer)
        json_data = dirtyjson.loads(extracted_json)
        return pydantic_model.model_validate(json_data)
    except Exception as e:
        raise ValueError(f"Issue with loading json format from LLM output: {e}")
