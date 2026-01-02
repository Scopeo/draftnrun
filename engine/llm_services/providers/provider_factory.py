import logging
from typing import Optional

from engine.llm_services.providers.base_provider import BaseProvider
from settings import settings

LOGGER = logging.getLogger(__name__)


def create_provider(
    provider: str,
    model_name: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseProvider:
    if api_key is None:
        match provider:
            case "openai":
                api_key = settings.OPENAI_API_KEY
            case "cerebras":
                api_key = settings.CEREBRAS_API_KEY
            case "google":
                api_key = settings.GOOGLE_API_KEY
            case "mistral":
                api_key = settings.MISTRAL_API_KEY
            case "anthropic":
                api_key = settings.ANTHROPIC_API_KEY
            case _:
                custom_models_dict = settings.custom_models.get("custom_models")
                if custom_models_dict is None:
                    raise ValueError("Custom models configuration not found in settings")
                config_provider = custom_models_dict.get(provider)
                if config_provider is None:
                    raise ValueError(f"Provider {provider} not found in settings")
                model_config = next(
                    (model for model in config_provider if model.get("model_name") == model_name), None
                )
                if model_config is None:
                    raise ValueError(f"Model {model_name} not found for provider {provider}")
                api_key = model_config.get("api_key")
                LOGGER.debug(f"Using custom api key for provider: {provider}")
                if api_key is None:
                    raise ValueError(f"API key must be provided for custom provider: {provider}")

    if base_url is None:
        match provider:
            case "openai":
                base_url = None
            case "cerebras":
                base_url = settings.CEREBRAS_BASE_URL
            case "google":
                base_url = settings.GOOGLE_BASE_URL
            case "mistral":
                base_url = settings.MISTRAL_BASE_URL
            case "anthropic":
                base_url = settings.ANTHROPIC_BASE_URL
            case _:
                custom_models_dict = settings.custom_models.get("custom_models")
                if custom_models_dict is None:
                    raise ValueError("Custom models configuration not found in settings")
                config_provider = custom_models_dict.get(provider)
                if config_provider is None:
                    raise ValueError(f"Provider {provider} not found in settings")
                model_config = next(
                    (model for model in config_provider if model.get("model_name") == model_name), None
                )
                if model_config is None:
                    raise ValueError(f"Model {model_name} not found for provider {provider}")
                base_url = model_config.get("base_url")
                LOGGER.debug(f"Using custom base url for provider: {provider}")
                if base_url is None:
                    raise ValueError(f"Base URL must be provided for custom provider: {provider}")

    match provider:
        case "openai":
            from engine.llm_services.providers.openai_provider import OpenAIProvider

            return OpenAIProvider(api_key, base_url, model_name, **kwargs)
        case "anthropic":
            from engine.llm_services.providers.anthropic_provider import AnthropicProvider

            return AnthropicProvider(api_key, base_url, model_name, **kwargs)
        case "google":
            from engine.llm_services.providers.google_provider import GoogleProvider

            return GoogleProvider(api_key, base_url, model_name, **kwargs)
        case "mistral":
            from engine.llm_services.providers.mistral_provider import MistralProvider

            return MistralProvider(api_key, base_url, model_name, **kwargs)
        case "cerebras":
            from engine.llm_services.providers.cerebras_provider import CerebrasProvider

            return CerebrasProvider(api_key, base_url, model_name, **kwargs)
        case _:
            from engine.llm_services.providers.custom_provider import CustomProvider

            return CustomProvider(api_key, base_url, model_name, provider, **kwargs)
