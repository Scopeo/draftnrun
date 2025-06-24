from typing import Any
import pytest
from ada_backend.services.entity_factory import build_llm_service_processor, get_llm_provider_and_model
from engine.llm_services.openai_llm_service import OpenAILLMService
from engine.llm_services.mistral_llm_service import MistralLLMService
from engine.llm_services.google_llm_service import GoogleLLMService
from tests.mocks.trace_manager import MockTraceManager


# List of all models defined in the system (from ada_backend/database/seed/utils.py)
AVAILABLE_MODELS = [
    # OpenAI models
    "openai:gpt-4.1",
    "openai:gpt-4.1-mini", 
    "openai:gpt-4.1-nano",
    "openai:gpt-4o",
    "openai:gpt-4o-mini",
    "openai:o4-mini-2025-04-16",  # Should have temperature 1.0
    "openai:o3-2025-04-16",       # Should have temperature 1.0
    # Add other providers when they are enabled
    # "mistral:mistral-large",
    # "mistral:mistral-small-3", 
    # "google:gemini-2.0-flash",
]

# Models that require temperature = 1.0
MODELS_REQUIRING_HIGH_TEMPERATURE = [
    "o4-mini-2025-04-16",
    "o3-2025-04-16"
]


class TestModelTemperatureValidation:
    """Test suite to validate all models work correctly and have appropriate default temperatures."""
    
    def test_get_llm_provider_and_model_parsing(self):
        """Test that model string parsing works correctly for all providers."""
        test_cases = [
            ("openai:gpt-4o", ("openai", "gpt-4o")),
            ("openai:o4-mini-2025-04-16", ("openai", "o4-mini-2025-04-16")),
            ("openai:o3-2025-04-16", ("openai", "o3-2025-04-16")),
            ("mistral:mistral-large", ("mistral", "mistral-large")),
            ("google:gemini-2.0-flash", ("google", "gemini-2.0-flash")),
        ]
        
        for model_string, expected in test_cases:
            provider, model = get_llm_provider_and_model(model_string)
            assert provider == expected[0], f"Provider mismatch for {model_string}"
            assert model == expected[1], f"Model mismatch for {model_string}"
    
    def test_invalid_model_format(self):
        """Test that invalid model formats raise appropriate errors."""
        with pytest.raises(ValueError, match="Invalid LLM model format"):
            get_llm_provider_and_model("invalid-format")
        
        with pytest.raises(ValueError, match="Format invalide pour llm_model"):
            get_llm_provider_and_model("too:many:colons:here")
    
    @pytest.mark.parametrize("model_string", AVAILABLE_MODELS)
    def test_all_models_can_be_instantiated(self, model_string):
        """Test that all models in the system can be successfully instantiated."""
        trace_manager = MockTraceManager(project_name="test_project")
        processor = build_llm_service_processor(trace_manager)  # type: ignore
        
        # Test model instantiation
        params = {"llm_model": model_string}
        constructor_params = {"llm_service": None}  # Mock constructor params
        
        try:
            processed_params = processor(params, constructor_params)
            llm_service = processed_params["llm_service"]
            
            # Verify the service was created
            assert llm_service is not None, f"LLM service not created for {model_string}"
            
            # Verify the correct provider service is used
            provider, model_name = get_llm_provider_and_model(model_string)
            if provider == "openai":
                assert isinstance(llm_service, OpenAILLMService)
                assert llm_service._completion_model == model_name
            elif provider == "mistral":
                assert isinstance(llm_service, MistralLLMService)
                assert llm_service._completion_model == model_name
            elif provider == "google":
                assert isinstance(llm_service, GoogleLLMService) 
                assert llm_service._completion_model == model_name
            
        except Exception as e:
            pytest.fail(f"Failed to instantiate model {model_string}: {str(e)}")
    
    def test_o4_mini_and_o3_models_have_correct_temperature(self):
        """Test that o4-mini and o3 models have default temperature of 1.0."""
        trace_manager = MockTraceManager(project_name="test_project")
        processor = build_llm_service_processor(trace_manager)  # type: ignore
        
        for model_string in ["openai:o4-mini-2025-04-16", "openai:o3-2025-04-16"]:
            params = {"llm_model": model_string}
            constructor_params = {"llm_service": None}
            
            processed_params = processor(params, constructor_params)
            llm_service = processed_params["llm_service"]
            
            assert llm_service._default_temperature == 1.0, \
                f"Model {model_string} should have temperature 1.0, got {llm_service._default_temperature}"
    
    def test_other_openai_models_have_standard_temperature(self):
        """Test that other OpenAI models have the standard default temperature of 0.3."""
        trace_manager = MockTraceManager(project_name="test_project")
        processor = build_llm_service_processor(trace_manager)  # type: ignore
        
        standard_models = [
            "openai:gpt-4.1",
            "openai:gpt-4.1-mini",
            "openai:gpt-4.1-nano", 
            "openai:gpt-4o",
            "openai:gpt-4o-mini"
        ]
        
        for model_string in standard_models:
            params = {"llm_model": model_string}
            constructor_params = {"llm_service": None}
            
            processed_params = processor(params, constructor_params)
            llm_service = processed_params["llm_service"]
            
            assert llm_service._default_temperature == 0.3, \
                f"Model {model_string} should have temperature 0.3, got {llm_service._default_temperature}"
    
    def test_explicit_temperature_overrides_default(self):
        """Test that explicitly provided temperature overrides model defaults."""
        trace_manager = MockTraceManager(project_name="test_project")
        processor = build_llm_service_processor(trace_manager)  # type: ignore
        
        # Test with o4-mini (normally would get 1.0, but we override to 0.5)
        params = {
            "llm_model": "openai:o4-mini-2025-04-16",
            "llm_temperature": 0.5
        }
        constructor_params = {"llm_service": None}
        
        processed_params = processor(params, constructor_params)
        llm_service = processed_params["llm_service"]
        
        assert llm_service._default_temperature == 0.5, \
            f"Explicit temperature should override default, got {llm_service._default_temperature}"
        
        # Test with standard model (normally would get 0.3, but we override to 0.8)
        params = {
            "llm_model": "openai:gpt-4o",
            "llm_temperature": 0.8
        }
        
        processed_params = processor(params, constructor_params)
        llm_service = processed_params["llm_service"]
        
        assert llm_service._default_temperature == 0.8, \
            f"Explicit temperature should override default, got {llm_service._default_temperature}"
    
    def test_unsupported_provider_raises_error(self):
        """Test that unsupported providers raise appropriate errors."""
        trace_manager = MockTraceManager(project_name="test_project")
        processor = build_llm_service_processor(trace_manager)  # type: ignore
        
        params = {"llm_model": "unsupported:some-model"}
        constructor_params = {"llm_service": None}
        
        with pytest.raises(ValueError, match="Unsupported LLM provider: unsupported"):
            processor(params, constructor_params)
    
    def test_additional_parameters_are_passed_correctly(self):
        """Test that additional parameters like API key and embedding model are handled correctly."""
        trace_manager = MockTraceManager(project_name="test_project")
        processor = build_llm_service_processor(trace_manager)  # type: ignore
        
        params = {
            "llm_model": "openai:gpt-4o",
            "llm_api_key": "test-api-key",
            "embedding_model_name": "text-embedding-3-large"
        }
        constructor_params = {"llm_service": None}
        
        processed_params = processor(params, constructor_params)
        llm_service = processed_params["llm_service"]
        
        # Note: These are passed to the constructor but we can't easily test them
        # as they are used internally. The important thing is no error is raised.
        assert llm_service is not None
        assert isinstance(llm_service, OpenAILLMService)


if __name__ == "__main__":
    pytest.main([__file__])