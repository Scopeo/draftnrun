"""
Capability matrix defining which models support which features for each provider.

For each provider, capabilities are organized by:
- text: Text-only operations (completion, function calling)
- vision: Operations that can handle images
- specialized: Provider-specific capabilities (embedding, OCR, web search)

Each capability maps to a list of model names to test:
- Non-empty list: Test with these specific models
- Empty list []: Provider doesn't support this capability (test will be skipped)

This allows testing:
- Multiple models per capability (e.g., test both gpt-5-mini)
- Different models for different capabilities (e.g., pixtral-12b for vision, pixtral-large for OCR)
"""

CAPABILITY_MATRIX = {
    "openai": {
        "text": {
            "complete": ["gpt-5-mini"],
            "complete_structured_pydantic": ["gpt-5-mini"],
            "complete_structured_json_schema": ["gpt-5-mini"],
            "function_call": ["gpt-5-mini"],
            "function_call_structured": ["gpt-5-mini"],
            "function_call_multi_turn": ["gpt-5-mini"],
            "function_call_tool_choice_none": ["gpt-5-mini"],
            "function_call_empty_tools": ["gpt-5-mini"],
            "function_call_with_system": ["gpt-5-mini"],
            "function_call_both_tools_and_structured": ["gpt-5-mini"],
        },
        "vision": {
            "complete": ["gpt-5-mini"],
            "complete_structured": ["gpt-5-mini"],
            "function_call_structured": ["gpt-5-mini"],
        },
        "specialized": {
            "embedding": ["text-embedding-3-small"],
            "embedding_async": ["text-embedding-3-small"],
            "ocr": [],
            "web_search": ["gpt-5-mini"],
        },
    },
    "google": {
        "text": {
            "complete": ["gemini-2.0-flash-lite"],
            "complete_structured_pydantic": ["gemini-2.0-flash-lite"],
            "complete_structured_json_schema": ["gemini-2.0-flash-lite"],
            "function_call": ["gemini-2.0-flash-lite"],
            "function_call_structured": ["gemini-2.0-flash-lite"],
            "function_call_multi_turn": ["gemini-2.0-flash-lite"],
            "function_call_tool_choice_none": ["gemini-2.0-flash-lite"],
            "function_call_empty_tools": ["gemini-2.0-flash-lite"],
            "function_call_with_system": ["gemini-2.0-flash-lite"],
            "function_call_both_tools_and_structured": ["gemini-2.0-flash-lite"],
        },
        "vision": {
            "complete": ["gemini-2.0-flash-lite"],
            "complete_structured": ["gemini-2.0-flash-lite"],
            "function_call_structured": ["gemini-2.0-flash-lite"],
        },
        "specialized": {
            "embedding": [],
            "embedding_async": [],
            "ocr": [],
            "web_search": [],
        },
    },
    "cerebras": {
        "text": {
            "complete": ["llama-3.3-70b", "qwen-3-32b"],
            "complete_structured_pydantic": ["llama-3.3-70b", "qwen-3-32b"],
            "complete_structured_json_schema": ["llama-3.3-70b", "qwen-3-32b"],
            "function_call": ["llama-3.3-70b", "qwen-3-32b"],
            "function_call_structured": ["llama-3.3-70b", "qwen-3-32b"],
            "function_call_multi_turn": ["llama-3.3-70b", "qwen-3-32b"],
            "function_call_tool_choice_none": ["llama-3.3-70b", "qwen-3-32b"],
            "function_call_empty_tools": ["llama-3.3-70b", "qwen-3-32b"],
            "function_call_with_system": ["llama-3.3-70b", "qwen-3-32b"],
            "function_call_both_tools_and_structured": ["llama-3.3-70b", "qwen-3-32b"],
        },
        "vision": {
            "complete": [],
            "complete_structured": [],
            "function_call_structured": [],
        },
        "specialized": {
            "embedding": [],
            "embedding_async": [],
            "ocr": [],
            "web_search": [],
        },
    },
    "mistral": {
        "text": {
            "complete": ["mistral-small-latest"],
            "complete_structured_pydantic": ["mistral-small-latest"],
            "complete_structured_json_schema": ["mistral-small-latest"],
            "function_call": ["mistral-small-latest"],
            "function_call_structured": ["mistral-small-latest"],
            "function_call_multi_turn": ["mistral-small-latest"],
            "function_call_tool_choice_none": ["mistral-small-latest"],
            "function_call_empty_tools": ["mistral-small-latest"],
            "function_call_with_system": ["mistral-small-latest"],
            "function_call_both_tools_and_structured": ["mistral-small-latest"],
        },
        "vision": {
            "complete": ["mistral-small-latest"],
            "complete_structured": ["mistral-small-latest"],
            "function_call_structured": ["mistral-small-latest"],
        },
        "specialized": {
            "embedding": [],
            "embedding_async": [],
            "ocr": ["mistral-ocr-latest"],
            "web_search": [],
        },
    },
    "anthropic": {
        "text": {
            "complete": ["claude-haiku-4-5-20251001"],
            "complete_structured_pydantic": ["claude-haiku-4-5-20251001"],
            "complete_structured_json_schema": ["claude-haiku-4-5-20251001"],
            "function_call": ["claude-haiku-4-5-20251001"],
            "function_call_structured": ["claude-haiku-4-5-20251001"],
            "function_call_multi_turn": ["claude-haiku-4-5-20251001"],
            "function_call_tool_choice_none": ["claude-haiku-4-5-20251001"],
            "function_call_empty_tools": ["claude-haiku-4-5-20251001"],
            "function_call_with_system": ["claude-haiku-4-5-20251001"],
            "function_call_both_tools_and_structured": ["claude-haiku-4-5-20251001"],
        },
        "vision": {
            "complete": ["claude-haiku-4-5-20251001"],
            "complete_structured": ["claude-haiku-4-5-20251001"],
            "function_call_structured": ["claude-haiku-4-5-20251001"],
        },
        "specialized": {
            "embedding": [],
            "embedding_async": [],
            "ocr": [],
            "web_search": [],
        },
    },
}


def get_provider_model_pairs(modality: str, capability: str) -> list[tuple[str, str]]:
    """
    Returns list of (provider, model) tuples for pytest parametrization.
    Automatically filters out providers with empty model lists.

    Args:
        modality: One of "text", "vision", "specialized"
        capability: Specific capability key (e.g., "complete", "function_call_structured")

    Returns:
        List of (provider_name, model_name) tuples

    Example:
        >>> get_provider_model_pairs("text", "complete")
        [("openai", "gpt-5-mini"), ("google", "gemini-2.0-flash-lite"), ...]
    """
    pairs = []
    for provider, capabilities in CAPABILITY_MATRIX.items():
        models = capabilities.get(modality, {}).get(capability, [])
        for model in models:
            pairs.append((provider, model))
    return pairs


def get_provider_required_settings(provider: str) -> tuple[str, ...]:
    """
    Returns tuple of required environment variable names for a provider.

    Args:
        provider: Provider name (e.g., "openai", "google")

    Returns:
        Tuple of required setting names
    """
    if provider == "openai":
        return ("OPENAI_API_KEY",)
    if provider == "google":
        return ("GOOGLE_API_KEY", "GOOGLE_BASE_URL")
    if provider == "cerebras":
        return ("CEREBRAS_API_KEY", "CEREBRAS_BASE_URL")
    if provider == "mistral":
        return ("MISTRAL_API_KEY",)
    if provider == "anthropic":
        return ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL")
    raise ValueError(f"Unknown provider: {provider}")


def get_all_providers() -> list[str]:
    return list(CAPABILITY_MATRIX.keys())


def get_capability_display_name(modality: str, capability: str) -> str:
    """
    Returns human-readable display name for a capability.

    Args:
        modality: One of "text", "vision", "specialized"
        capability: Capability key

    Returns:
        Display name for reports/tables
    """
    modality_prefix = {
        "text": "Text",
        "vision": "Vision",
        "specialized": "Specialized",
    }.get(modality, modality.title())

    capability_names = {
        "complete": "Complete",
        "complete_structured_pydantic": "Complete + Structured (Pydantic)",
        "complete_structured_json_schema": "Complete + Structured (JSON Schema)",
        "function_call": "Function Call",
        "function_call_structured": "Function Call + Structured Output",
        "function_call_multi_turn": "Function Call (Multi-turn)",
        "function_call_tool_choice_none": "Function Call (tool_choice=none)",
        "function_call_empty_tools": "Function Call (empty tools)",
        "function_call_with_system": "Function Call (with system message)",
        "function_call_both_tools_and_structured": "Function Call (tools + structured)",
        "embedding": "Embedding",
        "embedding_async": "Embedding (async)",
        "ocr": "OCR",
        "web_search": "Web Search",
    }.get(capability, capability.replace("_", " ").title())

    return f"{modality_prefix} / {capability_names}"
