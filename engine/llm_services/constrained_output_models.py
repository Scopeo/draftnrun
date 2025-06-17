from typing import Dict, List, Optional, Union, Literal
from pydantic import BaseModel, RootModel


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
