import pytest
from unittest.mock import AsyncMock, MagicMock
from engine.llm_services.openai_llm_service import OpenAILLMService


@pytest.fixture
def mock_service():
    mock_trace = MagicMock()
    service = OpenAILLMService(trace_manager=mock_trace)
    service._client = MagicMock()
    service._async_client = MagicMock()
    return service


def test_embed(mock_service):
    mock_service._client.embeddings.create.return_value.data = ["mock_embedding"]
    result = mock_service.embed("hello")
    assert result == ["mock_embedding"]


def test_complete(mock_service):
    mock_service._client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="hi"))
    ]
    result = mock_service.complete([{"role": "user", "content": "hello"}])
    assert result == "hi"


def test_web_search(mock_service):
    mock_service._client.responses.create.return_value.output_text = "search result"
    result = mock_service.web_search("query")
    assert result == "search result"


def test_function_call_without_trace(mock_service):
    mock_service._client.chat.completions.create.return_value = "mock_response"
    result = mock_service._function_call_without_trace([{"role": "user", "content": "hi"}])
    assert result == "mock_response"


def test_generate_transcript(mock_service, tmp_path):
    dummy_file = tmp_path / "audio.wav"
    dummy_file.write_bytes(b"dummy audio")
    mock_service._client.audio.transcriptions.create.return_value = "transcript"
    result = mock_service.generate_transcript(str(dummy_file), "en")
    assert result == "transcript"


def test_generate_speech_from_text(mock_service, tmp_path):
    output_file = tmp_path / "speech.wav"
    mock_write = MagicMock()
    mock_service._client.audio.speech.create.return_value.write_to_file = mock_write
    result = mock_service.generate_speech_from_text("hello", str(output_file))
    mock_write.assert_called_once()
    assert result == str(output_file)


def test_get_token_size(mock_service):
    mock_service._completion_model = "gpt-4"
    result = mock_service.get_token_size("hello world")
    assert isinstance(result, int)
    assert result > 0


@pytest.mark.asyncio
async def test_aembed(mock_service):
    mock_service._async_client.embeddings.create = AsyncMock(return_value=MagicMock(data=["async_embedding"]))
    result = await mock_service.aembed("test input")
    assert result == ["async_embedding"]


@pytest.mark.asyncio
async def test_acomplete(mock_service):
    mock_service._async_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="async hello"))])
    )
    result = await mock_service.acomplete([{"role": "user", "content": "hello"}])
    assert result == "async hello"


@pytest.mark.asyncio
async def test_aweb_search(mock_service):
    mock_service._async_client.responses.create = AsyncMock(return_value=MagicMock(output_text="web result"))
    result = await mock_service.aweb_search("query")
    assert result == "web result"


@pytest.mark.asyncio
async def test_afunction_call_without_trace(mock_service):
    mock_service._async_client.chat.completions.create = AsyncMock(return_value="async call result")
    result = await mock_service.afunction_call_without_trace([{"role": "user", "content": "hi"}])
    assert result == "async call result"


@pytest.mark.asyncio
async def test_agenerate_transcript(mock_service, tmp_path):
    dummy_file = tmp_path / "audio.wav"
    dummy_file.write_bytes(b"audio content")
    mock_service._async_client.audio.transcriptions.create = AsyncMock(return_value="async transcript")
    result = await mock_service.agenerate_transcript(str(dummy_file), "en")
    assert result == "async transcript"


@pytest.mark.asyncio
async def test_agenerate_speech_from_text(mock_service, tmp_path):
    output_file = tmp_path / "speech.wav"
    mock_read = AsyncMock(return_value=b"audio")
    mock_response = MagicMock(aread=mock_read)
    mock_service._async_client.audio.speech.create = AsyncMock(return_value=mock_response)
    result = await mock_service.agenerate_speech_from_text("text", str(output_file))
    assert result == str(output_file)
    mock_read.assert_awaited()
