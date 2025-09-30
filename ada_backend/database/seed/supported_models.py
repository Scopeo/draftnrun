from typing import List, Dict, Any


class ModelCapability:
    """Constants for model capabilities"""

    FILE = "file"
    IMAGE = "image"
    CONSTRAINED_OUTPUT = "constrained_output"
    FUNCTION_CALLING = "function_calling"
    WEB_SEARCH = "web_search"
    OCR = "ocr"
    EMBEDDING = "embedding"
    COMPLETION = "completion"
    REASONING = "reasoning"


# Comprehensive model definitions with capabilities
ALL_SUPPORTED_MODELS = [
    # OpenAI Models
    {
        "name": "GPT-5",
        "reference": "openai:gpt-5",
        "provider": "openai",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.FILE,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.WEB_SEARCH,
            ModelCapability.REASONING,
        ],
    },
    {
        "name": "GPT-5 Nano",
        "reference": "openai:gpt-5-nano",
        "provider": "openai",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.FILE,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.WEB_SEARCH,
            ModelCapability.REASONING,
        ],
    },
    {
        "name": "GPT-5 Mini",
        "reference": "openai:gpt-5-mini",
        "provider": "openai",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.FILE,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.WEB_SEARCH,
            ModelCapability.REASONING,
        ],
    },
    {
        "name": "GPT-4.1",
        "reference": "openai:gpt-4.1",
        "provider": "openai",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.FILE,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.WEB_SEARCH,
        ],
    },
    {
        "name": "GPT-4.1 Mini",
        "reference": "openai:gpt-4.1-mini",
        "provider": "openai",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.FILE,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.WEB_SEARCH,
        ],
    },
    {
        "name": "GPT-4.1 Nano",
        "reference": "openai:gpt-4.1-nano",
        "provider": "openai",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.IMAGE,
            ModelCapability.FILE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    {
        "name": "GPT-4o",
        "reference": "openai:gpt-4o",
        "provider": "openai",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.IMAGE,
            ModelCapability.FILE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.WEB_SEARCH,
        ],
    },
    {
        "name": "GPT-4o Mini",
        "reference": "openai:gpt-4o-mini",
        "provider": "openai",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.IMAGE,
            ModelCapability.FILE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.WEB_SEARCH,
        ],
    },
    # Google Gemini Models
    {
        "name": "Gemini 2.5 Pro",
        "reference": "google:gemini-2.5-pro-preview-06-05",
        "provider": "google",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    {
        "name": "Gemini 2.5 Flash",
        "reference": "google:gemini-2.5-flash-preview-05-20",
        "provider": "google",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    {
        "name": "Gemini 2.0 Flash",
        "reference": "google:gemini-2.0-flash",
        "provider": "google",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    {
        "name": "Gemini 2.0 Flash lite",
        "reference": "google:gemini-2.0-flash-lite",
        "provider": "google",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.IMAGE,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    # Cerebras Models
    {
        "name": "Llama 3.3 70B (Cerebras)",
        "reference": "cerebras:llama-3.3-70b",
        "provider": "cerebras",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    {
        "name": "Qwen 3 235B Instruct (Cerebras)",
        "reference": "cerebras:qwen-3-235b-a22b-instruct-2507",
        "provider": "cerebras",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    {
        "name": "Qwen 3 32B (Cerebras)",
        "reference": "cerebras:qwen-3-32b",
        "provider": "cerebras",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            # Model is reasoning by default
        ],
    },
    {
        "name": "OpenAI GPT OSS (Cerebras)",
        "reference": "cerebras:gpt-oss-120b",
        "provider": "cerebras",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            # TODO : handle cerebras for reasoning
        ],
    },
    # Mistral Models
    {
        "name": "Mistral Large 2411",
        "reference": "mistral:mistral-large-latest",
        "provider": "mistral",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    {
        "name": "Mistral Medium 2505",
        "reference": "mistral:mistral-medium-latest",
        "provider": "mistral",
        "capabilities": [
            ModelCapability.COMPLETION,
            ModelCapability.CONSTRAINED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
        ],
    },
    {
        "name": "Mistral OCR 2505",
        "reference": "mistral:mistral-ocr-latest",
        "provider": "mistral",
        "capabilities": [
            ModelCapability.OCR,
        ],
    },
    # OpenAI Embedding Models
    {
        "name": "Text Embedding 3 Large",
        "reference": "openai:text-embedding-3-large",
        "provider": "openai",
        "capabilities": [
            ModelCapability.EMBEDDING,
        ],
    },
]


def get_models_by_capability(*capabilities: str) -> List[Dict[str, Any]]:
    """
    Get all models that support ALL of the specified capabilities.

    Args:
        *capabilities: Variable number of capability strings to filter by

    Returns:
        List of model dictionaries that support all specified capabilities
    """
    if not capabilities:
        return ALL_SUPPORTED_MODELS.copy()

    return [
        model
        for model in ALL_SUPPORTED_MODELS
        if all(capability in model["capabilities"] for capability in capabilities)
    ]
