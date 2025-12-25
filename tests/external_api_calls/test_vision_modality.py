import base64
from unittest.mock import MagicMock

import pytest

from engine.agent.types import ToolDescription
from engine.llm_services.llm_service import CompletionService, VisionService
from .capability_matrix import get_provider_model_pairs, get_provider_required_settings
from .test_helpers import (
    skip_if_missing_settings,
    small_test_image_bytes_png,
    parse_possibly_double_encoded_json,
)


class TestVisionModality:
    class TestComplete:
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("vision", "complete"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        def test_basic_image_description(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = VisionService(
                trace_manager=MagicMock(),
                provider=provider,
                model_name=model,
            )
            image_bytes = small_test_image_bytes_png()
            response = service.get_image_description([image_bytes], "Describe the image in one word.")
            assert response is not None
            assert isinstance(response, str)
            assert response.strip() != ""

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("vision", "complete_structured"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        async def test_image_description_with_structured_output(self, provider: str, model: str) -> None:
            """
            Test vision with structured output.
            Tests proper image format conversion for different APIs:
            - OpenAI Responses API needs flattened image_url
            - Anthropic needs base64 image format with source object
            - Google needs proper JSON format prompting
            """
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)

            # Prepare image as base64 data URL (OpenAI Chat Completions format)
            image_bytes = small_test_image_bytes_png()
            b64_data = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:image/png;base64,{b64_data}"

            # Structured output tool
            structured_tool = ToolDescription(
                name="image_analysis",
                description="Structured image analysis",
                tool_properties={
                    "description": {"type": "string", "description": "Image description"},
                    "has_text": {"type": "boolean", "description": "Whether image contains text"},
                },
                required_tool_properties=["description", "has_text"],
            )

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image and say if it has text."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ]

            response = await service.function_call_async(
                messages=messages,
                tools=[],
                tool_choice="required",
                structured_output_tool=structured_tool,
            )

            assert response is not None
            content = response.choices[0].message.content
            assert isinstance(content, str) and content.strip()
            parsed = parse_possibly_double_encoded_json(content)
            assert "description" in parsed
            assert "has_text" in parsed

    class TestFunctionCall:
        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "provider,model",
            get_provider_model_pairs("vision", "function_call_structured"),
            ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else str(x),
        )
        async def test_vision_function_call_with_structured_output(self, provider: str, model: str) -> None:
            skip_if_missing_settings(*get_provider_required_settings(provider))
            service = CompletionService(trace_manager=MagicMock(), provider=provider, model_name=model)

            # Prepare image
            image_bytes = small_test_image_bytes_png()
            b64_data = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:image/png;base64,{b64_data}"

            # Structured output tool
            structured_tool = ToolDescription(
                name="analyze_image",
                description="Analyze image and extract information",
                tool_properties={
                    "contains_logo": {"type": "boolean", "description": "Whether image contains a logo"},
                    "main_color": {"type": "string", "description": "Main color in the image"},
                },
                required_tool_properties=["contains_logo", "main_color"],
            )

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this image: does it contain a logo? What's the main color?"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ]

            response = await service.function_call_async(
                messages=messages,
                tools=[],
                tool_choice="required",
                structured_output_tool=structured_tool,
            )

            assert response is not None
            content = response.choices[0].message.content
            assert isinstance(content, str) and content.strip()
            parsed = parse_possibly_double_encoded_json(content)
            assert "contains_logo" in parsed
            assert "main_color" in parsed
