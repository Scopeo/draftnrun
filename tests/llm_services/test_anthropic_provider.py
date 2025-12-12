import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from engine.llm_services.providers.anthropic_provider import AnthropicProvider


@pytest.fixture
def anthropic_provider():
    """Create an AnthropicProvider instance for testing"""
    provider = AnthropicProvider(
        model_name="claude-3-5-sonnet-20241022",
        api_key="test-api-key",
        base_url="https://api.anthropic.com/v1/messages",
    )
    return provider


def test_build_anthropic_text_messages_single_tool_result(anthropic_provider):
    """Test that a single tool result is properly formatted"""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_123", "content": "Sunny, 25°C"},
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    assert len(anthropic_messages) == 2
    # Assistant message with tool_use
    assert anthropic_messages[0]["role"] == "assistant"
    assert len(anthropic_messages[0]["content"]) == 1
    assert anthropic_messages[0]["content"][0]["type"] == "tool_use"
    assert anthropic_messages[0]["content"][0]["id"] == "call_123"
    assert anthropic_messages[0]["content"][0]["name"] == "get_weather"

    # User message with single tool_result
    assert anthropic_messages[1]["role"] == "user"
    assert len(anthropic_messages[1]["content"]) == 1
    assert anthropic_messages[1]["content"][0]["type"] == "tool_result"
    assert anthropic_messages[1]["content"][0]["tool_use_id"] == "call_123"
    assert anthropic_messages[1]["content"][0]["content"] == "Sunny, 25°C"


def test_build_anthropic_text_messages_parallel_tool_calls_batched(anthropic_provider):
    """Test that parallel tool calls are properly batched into a single user message"""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "London"}'},
                },
                {
                    "id": "call_3",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Tokyo"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Paris: Sunny, 25°C"},
        {"role": "tool", "tool_call_id": "call_2", "content": "London: Cloudy, 18°C"},
        {"role": "tool", "tool_call_id": "call_3", "content": "Tokyo: Rainy, 22°C"},
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    # Should have exactly 2 messages: assistant with tool_use and user with all tool_results batched
    assert len(anthropic_messages) == 2

    # First message: assistant with 3 tool_use blocks
    assert anthropic_messages[0]["role"] == "assistant"
    assert len(anthropic_messages[0]["content"]) == 3
    assert all(item["type"] == "tool_use" for item in anthropic_messages[0]["content"])
    assert anthropic_messages[0]["content"][0]["id"] == "call_1"
    assert anthropic_messages[0]["content"][1]["id"] == "call_2"
    assert anthropic_messages[0]["content"][2]["id"] == "call_3"

    # Second message: user with 3 tool_result blocks BATCHED TOGETHER
    assert anthropic_messages[1]["role"] == "user"
    assert len(anthropic_messages[1]["content"]) == 3, "All tool results should be batched in a single user message"
    assert all(item["type"] == "tool_result" for item in anthropic_messages[1]["content"])
    assert anthropic_messages[1]["content"][0]["tool_use_id"] == "call_1"
    assert anthropic_messages[1]["content"][0]["content"] == "Paris: Sunny, 25°C"
    assert anthropic_messages[1]["content"][1]["tool_use_id"] == "call_2"
    assert anthropic_messages[1]["content"][1]["content"] == "London: Cloudy, 18°C"
    assert anthropic_messages[1]["content"][2]["tool_use_id"] == "call_3"
    assert anthropic_messages[1]["content"][2]["content"] == "Tokyo: Rainy, 22°C"


def test_build_anthropic_text_messages_multi_turn_with_parallel_calls(anthropic_provider):
    """Test multi-turn conversation with parallel tool calls in multiple rounds"""
    messages = [
        {"role": "user", "content": "What's the weather in Paris and London?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "London"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Paris: Sunny, 25°C"},
        {"role": "tool", "tool_call_id": "call_2", "content": "London: Cloudy, 18°C"},
        {"role": "assistant", "content": "Paris is sunny at 25°C. London is cloudy at 18°C."},
        {"role": "user", "content": "Now check Tokyo and Berlin"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_3",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Tokyo"}'},
                },
                {
                    "id": "call_4",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Berlin"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_3", "content": "Tokyo: Rainy, 22°C"},
        {"role": "tool", "tool_call_id": "call_4", "content": "Berlin: Snowy, 2°C"},
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    # Expected structure:
    # 1. user
    # 2. assistant (with 2 tool_use)
    # 3. user (with 2 batched tool_result)
    # 4. assistant (text response)
    # 5. user
    # 6. assistant (with 2 tool_use)
    # 7. user (with 2 batched tool_result)
    assert len(anthropic_messages) == 7

    # First tool results should be batched
    assert anthropic_messages[2]["role"] == "user"
    assert len(anthropic_messages[2]["content"]) == 2
    assert all(item["type"] == "tool_result" for item in anthropic_messages[2]["content"])

    # Second tool results should be batched
    assert anthropic_messages[6]["role"] == "user"
    assert len(anthropic_messages[6]["content"]) == 2
    assert all(item["type"] == "tool_result" for item in anthropic_messages[6]["content"])


def test_build_anthropic_text_messages_system_prompt_extraction(anthropic_provider):
    """Test that system messages are extracted and batched correctly"""
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    assert system_prompt == "You are a helpful assistant."
    assert len(anthropic_messages) == 2  # Only user and assistant
    assert anthropic_messages[0]["role"] == "user"
    assert anthropic_messages[1]["role"] == "assistant"


def test_build_anthropic_text_messages_tool_results_flushed_before_user_message(anthropic_provider):
    """Test that pending tool results are flushed when a new user message arrives"""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Paris: Sunny, 25°C"},
        {"role": "user", "content": "Thanks! What about London?"},
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    # Should have: assistant, user (tool result), user (text message)
    assert len(anthropic_messages) == 3
    assert anthropic_messages[0]["role"] == "assistant"
    assert anthropic_messages[1]["role"] == "user"
    assert anthropic_messages[1]["content"][0]["type"] == "tool_result"
    assert anthropic_messages[2]["role"] == "user"
    assert anthropic_messages[2]["content"][0]["type"] == "text"


def test_build_anthropic_text_messages_empty_tool_content(anthropic_provider):
    """Test handling of tool messages with empty or non-string content"""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "delete_file", "arguments": '{"file": "test.txt"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": ""},  # Empty content
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    assert len(anthropic_messages) == 2
    assert anthropic_messages[1]["content"][0]["content"] == ""


def test_build_anthropic_text_messages_assistant_with_text_and_tool_calls(anthropic_provider):
    """Test assistant message with both text content and tool calls"""
    messages = [
        {
            "role": "assistant",
            "content": "Let me check the weather for you.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Paris: Sunny, 25°C"},
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    # Assistant message should include both text and tool_use
    assert anthropic_messages[0]["role"] == "assistant"
    assert len(anthropic_messages[0]["content"]) == 2
    assert anthropic_messages[0]["content"][0]["type"] == "text"
    assert anthropic_messages[0]["content"][0]["text"] == "Let me check the weather for you."
    assert anthropic_messages[0]["content"][1]["type"] == "tool_use"


@pytest.mark.asyncio
async def test_function_call_without_structured_output_batches_tool_results(anthropic_provider):
    """Test that function_call_without_structured_output properly batches tool results via the API"""
    messages = [
        {"role": "user", "content": "What's the weather in Paris and London?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "London"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Paris: Sunny, 25°C"},
        {"role": "tool", "tool_call_id": "call_2", "content": "London: Cloudy, 18°C"},
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]

    # Mock the httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "The weather is nice in both cities."}],
        "model": "claude-3-5-sonnet-20241022",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        response, prompt_tokens, completion_tokens, total_tokens = (
            await anthropic_provider.function_call_without_structured_output(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.7,
                stream=False,
            )
        )

        # Verify the request was made
        assert mock_client.post.called
        call_args = mock_client.post.call_args

        # Get the body that was sent to the API
        sent_body = call_args.kwargs["json"]

        # Verify that tool results are batched in a single user message
        sent_messages = sent_body["messages"]

        # Find the user message with tool_result blocks
        tool_result_messages = [
            msg for msg in sent_messages if msg["role"] == "user" and msg["content"][0]["type"] == "tool_result"
        ]

        # Should have exactly one user message with tool results
        assert len(tool_result_messages) == 1

        # That message should contain both tool results
        tool_results_content = tool_result_messages[0]["content"]
        assert len(tool_results_content) == 2
        assert all(item["type"] == "tool_result" for item in tool_results_content)
        assert tool_results_content[0]["tool_use_id"] == "call_1"
        assert tool_results_content[1]["tool_use_id"] == "call_2"

        # Verify response
        assert response is not None
        assert prompt_tokens == 100
        assert completion_tokens == 50


def test_build_anthropic_text_messages_with_url_images(anthropic_provider):
    """Test that HTTP/HTTPS URL images are properly converted to Anthropic's URL format"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/image.jpg"},
                },
            ],
        }
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    assert len(anthropic_messages) == 1
    assert anthropic_messages[0]["role"] == "user"
    assert len(anthropic_messages[0]["content"]) == 2

    assert anthropic_messages[0]["content"][0]["type"] == "text"
    assert anthropic_messages[0]["content"][0]["text"] == "What's in this image?"

    assert anthropic_messages[0]["content"][1]["type"] == "image"
    assert anthropic_messages[0]["content"][1]["source"]["type"] == "url"
    assert anthropic_messages[0]["content"][1]["source"]["url"] == "https://example.com/image.jpg"


def test_build_anthropic_text_messages_with_data_url_images(anthropic_provider):
    """Test that data URL images are properly converted to Anthropic's base64 format"""
    data_url = "data:image/png;base64,iVBORw0KGgo="
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                },
            ],
        }
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    assert len(anthropic_messages) == 1
    assert anthropic_messages[0]["role"] == "user"
    assert len(anthropic_messages[0]["content"]) == 2

    assert anthropic_messages[0]["content"][0]["type"] == "text"
    assert anthropic_messages[0]["content"][1]["type"] == "image"
    assert anthropic_messages[0]["content"][1]["source"]["type"] == "base64"
    assert anthropic_messages[0]["content"][1]["source"]["media_type"] == "image/png"
    assert anthropic_messages[0]["content"][1]["source"]["data"] == "iVBORw0KGgo="


def test_build_anthropic_text_messages_with_mixed_images(anthropic_provider):
    """Test that both URL and data URL images can be used together"""
    data_url = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Compare these images"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/image1.jpg"},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "http://example.com/image2.png"},
                },
            ],
        }
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    assert len(anthropic_messages) == 1
    assert anthropic_messages[0]["role"] == "user"
    assert len(anthropic_messages[0]["content"]) == 4

    assert anthropic_messages[0]["content"][1]["type"] == "image"
    assert anthropic_messages[0]["content"][1]["source"]["type"] == "url"
    assert anthropic_messages[0]["content"][1]["source"]["url"] == "https://example.com/image1.jpg"

    assert anthropic_messages[0]["content"][2]["type"] == "image"
    assert anthropic_messages[0]["content"][2]["source"]["type"] == "base64"
    assert anthropic_messages[0]["content"][2]["source"]["media_type"] == "image/jpeg"

    assert anthropic_messages[0]["content"][3]["type"] == "image"
    assert anthropic_messages[0]["content"][3]["source"]["type"] == "url"
    assert anthropic_messages[0]["content"][3]["source"]["url"] == "http://example.com/image2.png"


def test_build_anthropic_text_messages_with_invalid_image_url(anthropic_provider, caplog):
    """Test that invalid image URLs are handled with a warning and dropped"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "ftp://example.com/image.jpg"},
                },
            ],
        }
    ]

    anthropic_messages, system_prompt = anthropic_provider._build_anthropic_text_messages(messages)

    assert len(anthropic_messages) == 1
    assert anthropic_messages[0]["role"] == "user"
    assert len(anthropic_messages[0]["content"]) == 1

    assert "Unsupported image URL format for Anthropic" in caplog.text
