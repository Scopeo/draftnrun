import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

from openai.types.chat import ChatCompletion
from pydantic import BaseModel

LOGGER = logging.getLogger(__name__)


class BaseProvider(ABC):
    def __init__(self, api_key: str, base_url: Optional[str], model_name: str, **kwargs):
        self._api_key = api_key
        self._base_url = base_url
        self._model_name = model_name

        require_base_url = getattr(self, "_require_base_url", True)
        self._validate_credentials(require_base_url=require_base_url)

    def _validate_credentials(self, require_base_url: bool) -> None:
        provider_name = self.__class__.__name__.replace("Provider", "").upper()

        if self._api_key is None:
            raise ValueError(
                f"{provider_name}'s API key is not configured. "
                f"Cannot make {provider_name} API request without an API key. "
                f"Set the {provider_name}_API_KEY environment variable or pass api_key when creating the provider."
            )

        if require_base_url and self._base_url is None:
            raise ValueError(
                f"{provider_name}'s base URL is not configured. "
                f"Cannot make {provider_name} API request without a base URL. "
                f"Set the {provider_name}_BASE_URL environment variable or pass base_url when creating the provider."
            )

    @abstractmethod
    async def complete(
        self,
        messages: list[dict] | str,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        pass

    @abstractmethod
    async def embed(self, text: str | list[str], **kwargs) -> tuple[list[float] | list[list[float]], int, int, int]:
        pass

    @abstractmethod
    async def constrained_complete_with_pydantic(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[BaseModel, int, int, int]:
        pass

    @abstractmethod
    async def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: dict,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        pass

    @abstractmethod
    async def function_call_without_structured_output(
        self,
        messages: list[dict] | str,
        tools: list[dict],
        tool_choice: str,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[ChatCompletion, int, int, int]:
        pass

    @abstractmethod
    async def function_call_with_structured_output(
        self,
        messages: list[dict] | str,
        tools: list[dict],
        tool_choice: str,
        structured_output_tool: dict,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[ChatCompletion, int, int, int]:
        pass

    @abstractmethod
    async def web_search(
        self, query: str, allowed_domains: Optional[list[str]], **kwargs
    ) -> tuple[str, int, int, int]:
        pass

    @abstractmethod
    async def vision(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel],
        temperature: float,
        **kwargs,
    ) -> tuple[str | BaseModel, int, int, int]:
        pass

    @abstractmethod
    async def ocr(self, messages: list[dict], **kwargs) -> tuple[str, int, int, int]:
        pass

    def _convert_tool_call_to_content(self, response: ChatCompletion, tool_call) -> ChatCompletion:
        try:
            arguments = tool_call.function.arguments
            if isinstance(arguments, str):
                response.choices[0].message.content = arguments
            else:
                response.choices[0].message.content = json.dumps(arguments, ensure_ascii=False)
            response.choices[0].message.tool_calls = None
            return response
        except Exception as e:
            raise ValueError(f"Error parsing structured output tool response: {e}") from e

    def _filter_and_convert_structured_output_tool(
        self,
        response: ChatCompletion,
        structured_output_tool: dict,
    ) -> ChatCompletion:
        tools_called = response.choices[0].message.tool_calls

        if not tools_called:
            raise ValueError(
                f"No tools were called despite tool_choice='required'. "
                f"Expected at least the structured output tool '{structured_output_tool['function']['name']}' "
                f"to be called. Response content: {response.choices[0].message.content}"
            )

        if len(tools_called) > 1:
            tools_called_without_structured = []
            structured_output_call = None
            for call in tools_called:
                if call.function.name == structured_output_tool["function"]["name"]:
                    if structured_output_call is None:
                        structured_output_call = call
                    continue
                tools_called_without_structured.append(call)

            if not tools_called_without_structured and structured_output_call:
                return self._convert_tool_call_to_content(response, structured_output_call)

            response.choices[0].message.tool_calls = tools_called_without_structured
        else:
            if tools_called[0].function.name == structured_output_tool["function"]["name"]:
                return self._convert_tool_call_to_content(response, tools_called[0])

        return response
