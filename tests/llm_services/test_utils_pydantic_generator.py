from typing import Dict, List

import pytest
from pydantic import BaseModel

from data_ingestion.document.pdf_vision_ingestion import FileType, TableOfContent, TOCSections
from engine.llm_services.utils_pydantic_generator import build_generic_pydantic_instance_from_pydantic_model


@pytest.fixture
def get_address_model_class():
    class Address(BaseModel):
        street: str
        city: str
        zip_code: int
        is_active: bool
        latitude: float

    return Address


def test_pdf_vision_ingestion_pydantic_models():
    # Test FileType
    file_type = build_generic_pydantic_instance_from_pydantic_model(FileType)
    assert file_type.is_native_pdf is False
    assert file_type.is_converted_from_powerpoint is False

    # Test TOCSections
    toc_section = build_generic_pydantic_instance_from_pydantic_model(TOCSections)
    assert toc_section.title == "string"
    assert toc_section.page_number == 0
    assert toc_section.level == 0

    # Test TableOfContent
    toc = build_generic_pydantic_instance_from_pydantic_model(TableOfContent)
    assert len(toc.sections) == 1
    assert toc.sections[0].title == "string"
    assert toc.sections[0].page_number == 0
    assert toc.sections[0].level == 0


def test_complex_nested_model(get_address_model_class):
    Address = get_address_model_class

    class Contact(BaseModel):
        email: str
        phone: str
        is_verified: bool

    class User(BaseModel):
        name: str
        age: int
        is_active: bool
        score: float
        addresses: List[Address]
        contacts: Dict[str, Contact]
        primary_address: Address
        metadata: Dict[str, str]
        tags: List[str]
        settings: Dict[str, bool]

    user = build_generic_pydantic_instance_from_pydantic_model(User)

    assert user.name == "string"
    assert user.age == 0
    assert user.is_active is False
    assert user.score == 0.0

    assert len(user.addresses) == 1
    address = user.addresses[0]
    assert address.street == "string"
    assert address.city == "string"
    assert address.zip_code == 0
    assert address.is_active is False
    assert address.latitude == 0.0

    assert len(user.contacts) == 1
    assert "key" in user.contacts
    contact = user.contacts["key"]
    assert contact.email == "string"
    assert contact.phone == "string"
    assert contact.is_verified is False

    assert user.primary_address.street == "string"
    assert user.primary_address.city == "string"
    assert user.primary_address.zip_code == 0
    assert user.primary_address.is_active is False
    assert user.primary_address.latitude == 0.0

    assert user.metadata == {"key": "string"}

    assert user.tags == ["string"]

    assert user.settings == {"key": False}


def test_edge_cases(get_address_model_class):
    Address = get_address_model_class

    class EdgeCaseModel(BaseModel):
        empty_list: List[str]
        empty_dict: Dict[str, str]
        nested_empty: List[List[str]]
        deep_nested: List[List[List[Address]]]

    edge_model = build_generic_pydantic_instance_from_pydantic_model(EdgeCaseModel)

    assert edge_model.empty_list == ["string"]

    assert edge_model.empty_dict == {"key": "string"}

    assert edge_model.nested_empty == [["string"]]

    assert len(edge_model.deep_nested) == 1
    assert len(edge_model.deep_nested[0]) == 1
    assert len(edge_model.deep_nested[0][0]) == 1
    address = edge_model.deep_nested[0][0][0]
    assert address.street == "string"
    assert address.city == "string"
