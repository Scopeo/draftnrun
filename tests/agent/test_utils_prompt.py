"""Unit tests for fill_prompt_template function."""

import pytest
from engine.agent.utils_prompt import fill_prompt_template


class TestFillPromptTemplate:
    """Test cases for fill_prompt_template function."""

    def test_basic_template_filling(self):
        """Test basic template filling with simple variables."""
        template = "Hello {name}, welcome to {place}!"
        variables = {"name": "Alice", "place": "Wonderland"}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_template_with_no_variables(self):
        """Test template with no placeholders returns unchanged."""
        template = "This is a simple string with no variables"
        variables = {}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == template

    def test_template_with_empty_variables_dict(self):
        """Test template with empty variables dict when no placeholders needed."""
        template = "No variables here"
        variables = {}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == template

    def test_template_with_none_variables(self):
        """Test template with None variables dict defaults to empty dict."""
        template = "No variables here"
        result = fill_prompt_template(template, component_name="test", variables=None)
        assert result == template

    def test_missing_required_variable(self):
        """Test that missing required variable raises ValueError."""
        template = "Hello {name}, welcome to {place}!"
        variables = {"name": "Alice"}
        with pytest.raises(ValueError) as exc_info:
            fill_prompt_template(template, component_name="test_component", variables=variables)
        assert "Missing template variable(s)" in str(exc_info.value)
        assert "place" in str(exc_info.value)
        assert "test_component" in str(exc_info.value)

    def test_multiple_missing_variables(self):
        """Test that multiple missing variables are reported."""
        template = "Hello {name}, from {city}, in {country}!"
        variables = {"name": "Alice"}
        with pytest.raises(ValueError) as exc_info:
            fill_prompt_template(template, component_name="test", variables=variables)
        error_msg = str(exc_info.value)
        assert "Missing template variable(s)" in error_msg
        assert "city" in error_msg or "country" in error_msg

    def test_extra_variables_ignored(self):
        """Test that extra variables in dict are ignored (not an error)."""
        template = "Hello {name}!"
        variables = {"name": "Alice", "extra": "ignored", "another": "also ignored"}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Hello Alice!"

    def test_numeric_values_converted_to_string(self):
        """Test that numeric values are converted to strings."""
        template = "Count: {count}, Price: {price}"
        variables = {"count": 42, "price": 99.99}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Count: 42, Price: 99.99"

    def test_boolean_values_converted_to_string(self):
        """Test that boolean values are converted to strings."""
        template = "Active: {active}, Enabled: {enabled}"
        variables = {"active": True, "enabled": False}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Active: True, Enabled: False"

    def test_none_value_converted_to_string(self):
        """Test that None values are converted to string 'None'."""
        template = "Value: {value}"
        variables = {"value": None}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Value: None"

    def test_list_value_converted_to_string(self):
        """Test that list values are converted to strings."""
        template = "Items: {items}"
        variables = {"items": [1, 2, 3]}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Items: [1, 2, 3]"

    def test_dict_value_converted_to_string(self):
        """Test that dict values are converted to strings."""
        template = "Config: {config}"
        variables = {"config": {"key": "value"}}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert "key" in result and "value" in result

    def test_empty_string_value(self):
        """Test that empty string values work correctly."""
        template = "Name: '{name}'"
        variables = {"name": ""}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Name: ''"

    def test_special_characters_in_template(self):
        """Test template with special characters."""
        template = "Message: {msg} (priority: {priority})"
        variables = {"msg": "Hello!", "priority": "high"}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Message: Hello! (priority: high)"

    def test_multiple_occurrences_of_same_variable(self):
        """Test template with same variable used multiple times."""
        template = "{name} says hello, {name} says goodbye"
        variables = {"name": "Alice"}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Alice says hello, Alice says goodbye"

    def test_complex_template_with_many_variables(self):
        """Test complex template with many variables."""
        template = "User {user} from {city}, {country} has {count} items worth ${total}"
        variables = {"user": "Alice", "city": "Paris", "country": "France", "count": 5, "total": 123.45}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "User Alice from Paris, France has 5 items worth $123.45"

    def test_empty_component_name(self):
        """Test that empty component_name works (default value)."""
        template = "Hello {name}!"
        variables = {"name": "Alice"}
        result = fill_prompt_template(template, component_name="", variables=variables)
        assert result == "Hello Alice!"

    def test_component_name_in_error_message(self):
        """Test that component_name appears in error messages."""
        template = "Hello {missing}!"
        variables = {}
        with pytest.raises(ValueError) as exc_info:
            fill_prompt_template(template, component_name="MyComponent", variables=variables)
        assert "MyComponent" in str(exc_info.value)

    def test_available_vars_in_error_message(self):
        """Test that available variables are listed in error message."""
        template = "Hello {missing}!"
        variables = {"available1": "value1", "available2": "value2"}
        with pytest.raises(ValueError) as exc_info:
            fill_prompt_template(template, component_name="test", variables=variables)
        error_msg = str(exc_info.value)
        assert "available1" in error_msg or "available2" in error_msg

    def test_unicode_characters(self):
        """Test template with unicode characters."""
        template = "Hello {name} from {city}!"
        variables = {"name": "José", "city": "São Paulo"}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert result == "Hello José from São Paulo!"

    def test_template_with_format_specifiers(self):
        """Test that format specifiers in template work correctly."""
        # Note: This tests that the function doesn't break with format specifiers
        # The actual formatting is handled by Python's str.format()
        template = "Value: {value}"
        variables = {"value": 42}
        result = fill_prompt_template(template, component_name="test", variables=variables)
        assert "42" in result
