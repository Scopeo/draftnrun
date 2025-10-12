import pytest
from pydantic import BaseModel
from typing import Optional

from engine.llm_services.constrained_output_models import (
    search_for_json_object,
    convert_json_str_to_pydantic,
    format_prompt_with_pydantic_output,
)


class SampleModel(BaseModel):
    name: str
    age: int
    is_active: bool = True


class SampleModelOptional(BaseModel):
    name: str
    age: Optional[int] = None


class TestSearchForJsonObject:
    """Test cases for the search_for_json_object function."""

    def test_simple_json_object(self):
        """Test extraction of a simple JSON object."""
        text = 'Here is some text {"name": "John", "age": 30} and more text'
        result = search_for_json_object(text)
        expected = '{"name": "John", "age": 30}'
        assert result == expected

    def test_nested_json_object(self):
        """Test extraction of a nested JSON object."""
        text = 'Text {"name": "John", "address": {"city": "NYC", "zip": 10001}} more text'
        result = search_for_json_object(text)
        expected = '{"name": "John", "address": {"city": "NYC", "zip": 10001}}'
        assert result == expected

    def test_multiple_json_objects_returns_first_to_last(self):
        """Test that it returns from first '{' to last '}'."""
        text = 'Text {"first": "object"} and {"second": "object"} more text'
        result = search_for_json_object(text)
        expected = '{"first": "object"} and {"second": "object"}'
        assert result == expected

    def test_no_json_object(self):
        """Test string with no JSON object."""
        text = "This is just plain text with no JSON"
        result = search_for_json_object(text)
        assert result is None


class TestConvertJsonStrToPydantic:
    """Test cases for the convert_json_str_to_pydantic function."""

    def test_valid_json_conversion(self):
        """Test conversion of valid JSON string to Pydantic model."""
        json_str = 'Here is some text {"name": "John", "age": 30, "is_active": true} and more text'
        result = convert_json_str_to_pydantic(json_str, SampleModel)

        assert isinstance(result, SampleModel)
        assert result.name == "John"
        assert result.age == 30
        assert result.is_active is True

    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises ValueError."""
        json_str = "Text {invalid json} more text"

        with pytest.raises(ValueError, match="Issue with loading json format from LLM output"):
            convert_json_str_to_pydantic(json_str, SampleModel)

    def test_no_json_object_raises_error(self):
        """Test that text without JSON object raises ValueError."""
        json_str = "Just plain text with no JSON"

        with pytest.raises(ValueError, match="Issue with loading json format from LLM output"):
            convert_json_str_to_pydantic(json_str, SampleModel)

    def test_malformed_json_raises_error(self):
        """Test that malformed JSON raises ValueError."""
        json_str = 'Text {"name": "John", "age":} more text'  # missing value

        with pytest.raises(ValueError, match="Issue with loading json format from LLM output"):
            convert_json_str_to_pydantic(json_str, SampleModel)


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_full_workflow(self):
        """Test the complete workflow from prompt formatting to JSON extraction."""
        # Step 1: Format prompt with Pydantic model
        prompt = "Please provide user information:"
        formatted_prompt = format_prompt_with_pydantic_output(prompt, SampleModel)
        assert (
            formatted_prompt == "Please provide user information:\nOutput in the following "
            'JSON format:\n{\n  "name": "string",\n '
            ' "age": 0,\n  "is_active": false\n}\n'
        )

        # Step 2: Simulate LLM response (in real usage, this would come from LLM)
        mock_response = (
            'Here is the user data: {"name": "Alice", "age": 28, "is_active": false} and some additional text'
        )

        # Step 3: Extract JSON from response
        extracted_json = search_for_json_object(mock_response)
        assert extracted_json is not None

        # Step 4: Convert to Pydantic model
        result = convert_json_str_to_pydantic(mock_response, SampleModel)

        assert isinstance(result, SampleModel)
        assert result.name == "Alice"
        assert result.age == 28
        assert result.is_active is False
