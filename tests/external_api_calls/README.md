# External API Calls Test Suite

This test suite validates LLM provider integrations across different modalities and capabilities.

## Structure

The test suite is organized by modality (text, vision, specialized services):

```
tests/external_api_calls/
├── capability_matrix.py          # Capability definitions and model configurations
├── test_helpers.py                # Shared utilities and fixtures
├── test_text_modality.py          # Text-only operations
├── test_vision_modality.py        # Image input operations
├── test_specialized_services.py   # Embedding, OCR, web search
├── conftest.py                    # Result reporting and pytest configuration
└── external_api_calls_matrix.md   # Auto-generated capability matrix (after test run)
```

## Capability Matrix

The capability matrix (`capability_matrix.py`) defines which models to test for each provider and capability:

```python
CAPABILITY_MATRIX = {
    "openai": {
        "text": {
            "complete": ["gpt-4o-mini"],              # List of models to test
            "function_call": ["gpt-4o-mini"],         # Multiple models possible
            ...
        },
        "vision": {
            "complete": ["gpt-4o-mini"],
            ...
        },
        "specialized": {
            "embedding": ["text-embedding-3-small"],
            "ocr": [],                                 # Empty = not supported
            ...
        }
    },
    # ... more providers
}
```

### Key Features

1. **Multiple models per capability**: Test different model sizes/versions (e.g., Cerebras tests both `llama-3.3-70b` and `qwen-3-32b`)
2. **Different models for different capabilities**: e.g., `pixtral-large-latest` for vision, `mistral-ocr-latest` for OCR
3. **Empty list = not supported**: Cleaner than hardcoded N/A checks

## Running Tests

This project uses `uv` for dependency management and test execution.

### Run all tests
```bash
uv run pytest tests/external_api_calls/
```

### Run specific modality
```bash
uv run pytest tests/external_api_calls/test_text_modality.py
uv run pytest tests/external_api_calls/test_vision_modality.py
uv run pytest tests/external_api_calls/test_specialized_services.py
```

### Run specific capability
```bash
# Run all completion tests
uv run pytest tests/external_api_calls/ -k "test_basic_completion"

# Run all function calling tests
uv run pytest tests/external_api_calls/ -k "function_call"

# Run all structured output tests
uv run pytest tests/external_api_calls/ -k "structured"
```

### Run specific provider
```bash
# Run all OpenAI tests
uv run pytest tests/external_api_calls/ -k "openai"

# Run all Google tests
uv run pytest tests/external_api_calls/ -k "google"
```

### Run specific provider+model combination
```bash
# Run tests for OpenAI gpt-4o-mini
uv run pytest tests/external_api_calls/ -k "openai/gpt-4o-mini"

# Run tests for Cerebras llama model
uv run pytest tests/external_api_calls/ -k "cerebras/llama-3.3-70b"
```

## Test Parametrization

Tests are parametrized with `(provider, model)` tuples:

```python
@pytest.mark.parametrize(
    "provider,model",
    get_provider_model_pairs("text", "complete"),
    ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x)
)
def test_basic_completion(provider: str, model: str) -> None:
    ...
```

This creates separate test instances like:
- `test_basic_completion[openai/gpt-4o-mini]`
- `test_basic_completion[google/gemini-2.0-flash-lite]`
- etc.

## Result Matrix

After running tests, a markdown table is generated in `external_api_calls_matrix.md`:

| Capability | openai | google | cerebras | mistral | anthropic |
|------------|--------|--------|----------|---------|-----------|
| Text / Complete | ✅ gpt-4o-mini | ✅ gemini-2.0-flash-lite | ✅ llama-3.3-70b<br>✅ qwen-3-32b | ✅ mistral-small-latest | ✅ claude-haiku-4-5-20251001 |
| Text / Function Call | ✅ gpt-4o-mini | ✅ gemini-2.0-flash-lite | ✅ llama-3.3-70b<br>✅ qwen-3-32b | ✅ mistral-small-latest | ✅ claude-haiku-4-5-20251001 |
| Vision / Complete | ✅ gpt-4o-mini | ✅ gemini-2.0-flash-lite | N/A | ✅ pixtral-large-latest | ✅ claude-haiku-4-5-20251001 |
| Specialized / OCR | N/A | N/A | N/A | ✅ mistral-ocr-latest | N/A |

Legend:
- `✅ model-name` = Test passed for this model
- `❌ model-name` = Test failed for this model
- `N/A` = Provider doesn't support this capability

## Environment Configuration

Tests require provider API keys and configuration:

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Google
export GOOGLE_API_KEY="..."
export GOOGLE_BASE_URL="https://generativelanguage.googleapis.com"

# Anthropic
export ANTHROPIC_API_KEY="..."
export ANTHROPIC_BASE_URL="https://api.anthropic.com"

# Mistral
export MISTRAL_API_KEY="..."

# Cerebras
export CEREBRAS_API_KEY="..."
export CEREBRAS_BASE_URL="https://api.cerebras.ai"
```

### Optional Test Overrides

Override specific models for testing:

```bash
# Test different model for OpenAI completion
export EXTERNAL_TEST_OPENAI_COMPLETE_MODEL="gpt-4o"

# Test different model for Google function calling
export EXTERNAL_TEST_GOOGLE_FUNCTION_CALL_MODEL="gemini-pro"
```

Format: `EXTERNAL_TEST_{PROVIDER}_{CAPABILITY}_MODEL`

### Special Test Requirements

Some tests require additional configuration:

```bash
# Mistral OCR requires a reachable image URL
export EXTERNAL_TEST_MISTRAL_OCR_IMAGE_URL="https://example.com/test-image.png"
```

## Adding New Providers

1. Add provider to `CAPABILITY_MATRIX` in `capability_matrix.py`:
   ```python
   "new_provider": {
       "text": {
           "complete": ["model-name"],
           "function_call": ["model-name"],
           ...
       },
       "vision": {...},
       "specialized": {...}
   }
   ```

2. Add provider required settings in `get_provider_required_settings()`:
   ```python
   if provider == "new_provider":
       return ("NEW_PROVIDER_API_KEY", "NEW_PROVIDER_BASE_URL")
   ```

3. Run tests - they will automatically parametrize for the new provider

## Adding New Capabilities

1. Add capability to relevant providers in `CAPABILITY_MATRIX`:
   ```python
   "openai": {
       "text": {
           "new_capability": ["gpt-4o-mini"],
           ...
       }
   }
   ```

2. Add test in appropriate modality file (e.g., `test_text_modality.py`):
   ```python
   @pytest.mark.parametrize(
       "provider,model",
       get_provider_model_pairs("text", "new_capability"),
       ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x)
   )
   def test_new_capability(provider: str, model: str) -> None:
       ...
   ```

3. Add test function name mapping in `conftest.py` → `_infer_capability_from_nodeid()`:
   ```python
   capability_mapping = {
       ...
       "test_new_capability": "new_capability",
   }
   ```

4. Add display name in `capability_matrix.py` → `get_capability_display_name()`:
   ```python
   capability_names = {
       ...
       "new_capability": "New Capability",
   }
   ```

## Test Organization

### Text Modality (`test_text_modality.py`)
- `TestComplete`: Simple completion without tools
  - Basic completion
  - Structured output (Pydantic)
  - Structured output (JSON Schema)
- `TestFunctionCall`: Function calling capabilities
  - Basic function calling
  - With structured output
  - With system messages
  - Multi-turn conversations
  - Tool choice variations
  - Edge cases

### Vision Modality (`test_vision_modality.py`)
- `TestComplete`: Image description
  - Basic image description
  - Image description with structured output
- `TestFunctionCall`: Image analysis with tools
  - Vision + function calling + structured output

### Specialized Services (`test_specialized_services.py`)
- Embedding generation (sync/async)
- OCR text extraction
- Web search

## Best Practices

1. **Use appropriate capability keys**: Match capability names in tests to capability_matrix keys
2. **Test real edge cases**: Multi-turn, system messages, tool_choice variations
3. **Document special requirements**: E.g., OCR needs image URL
4. **Keep helpers shared**: Use `test_helpers.py` for common utilities
5. **Update conftest mapping**: When adding new test functions, update `_infer_capability_from_nodeid()`

