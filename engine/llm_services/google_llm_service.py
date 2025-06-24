from typing import Optional
from enum import Enum
import io

from openai import OpenAI, AsyncOpenAI
from google import genai
from google.genai.types import Content, Part, File, GenerateContentConfig, FileData, UploadFileConfig
from tenacity import retry, stop_after_attempt, wait_chain, wait_fixed

from settings import settings
from engine.llm_services.openai_llm_service import OpenAILLMService
from engine.trace.trace_manager import TraceManager

# Google LLM roles are user and assistant, not system
CONVERSION_ROLES = {
    "system": "user",
    "user": "user",
    "assistant": "assistant",
}


class TypeFileToUpload(str, Enum):
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def __init__(self, value: str):
        self._value_ = value


class GoogleLLMService(OpenAILLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        model_name: str = "gemini-2.0-flash-exp",
        embedding_model: str = "gemini-embedding-exp-03-07",
        api_key: Optional[str] = settings.GOOGLE_API_KEY,
        base_url: Optional[str] = settings.GOOGLE_BASE_URL,
        default_temperature: float = 0.3,
    ):
        super().__init__(
            trace_manager=trace_manager,
            model_name=model_name,
            embedding_model_name=embedding_model,
            default_temperature=default_temperature,
            base_url=base_url,
            api_key=api_key,
        )
        super().__init__(trace_manager)
        self._completion_model = model_name
        self._embedding_model = embedding_model
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._google_client = genai.Client(api_key=api_key)

    def upload_file(self, file: str | bytes, type_of_file: TypeFileToUpload) -> File:
        """Upload a file to Google's Gemini API.

        Args:
            file: Either a file path (str) or file content (bytes)
            type_of_file: The type of file to upload

        Returns:
            File: The uploaded file object

        Raises:
            ValueError: If file is not a string path or bytes

        Parameters
        ----------
        type_of_file
        """
        if isinstance(file, str):
            # Direct file path upload
            sample_file = self._google_client.files.upload(
                file=file,
            )
            return sample_file

        elif isinstance(file, bytes):
            # Create BytesIO object from bytes
            bytes_io = io.BytesIO(file)
            # Upload using BytesIO
            sample_file = self._google_client.files.upload(
                file=bytes_io,
                config=UploadFileConfig(mime_type=type_of_file.value),  # Must specify mime_type for IOBase
            )
            return sample_file

        raise ValueError("File must be a string path or bytes")

    @retry(wait=wait_chain(wait_fixed(5), wait_fixed(20), wait_fixed(40), wait_fixed(60)), stop=stop_after_attempt(5))
    def complete_with_files(
        self,
        messages: list[dict],
        files: list[File],
        temperature: float = 0.0,
    ) -> str:
        contents = [
            Content(
                role="user",
                parts=[
                    Part(
                        file_data=FileData(
                            file_uri=file.uri,
                            mime_type=file.mime_type,
                        )
                    )
                    for file in files
                ],
            )
        ]
        contents.extend(
            [
                Content(role=CONVERSION_ROLES[message["role"]], parts=[Part(text=message["content"])])
                for message in messages
            ]
        )

        response = self._google_client.models.generate_content(
            model=self._completion_model, contents=contents, config=GenerateContentConfig(temperature=temperature)
        )

        return response.text

    @retry(wait=wait_chain(wait_fixed(5), wait_fixed(20), wait_fixed(40), wait_fixed(60)), stop=stop_after_attempt(5))
    async def async_complete_with_files(
        self,
        messages: list[dict],
        files: list[File],
        temperature: float = 0.0,
    ) -> str:
        contents = [
            Content(
                role="user",
                parts=[
                    Part(
                        file_data=FileData(
                            file_uri=file.uri,
                            mime_type=file.mime_type,
                        )
                    )
                    for file in files
                ],
            )
        ]
        contents.extend(
            [
                Content(role=CONVERSION_ROLES[message["role"]], parts=[Part(text=message["content"])])
                for message in messages
            ]
        )

        response = await self._google_client.aio.models.generate_content(
            model=self._completion_model,
            contents=contents,
            config=GenerateContentConfig(temperature=temperature)
        )

        return response.text

    def delete_file(self, file: File) -> None:
        """Delete a previously uploaded file.

        Args:
            file (File): The File object returned from upload_file()
        """
        self._google_client.files.delete(name=file.name)

    def list_files(self) -> list[File]:
        """List all files that have been uploaded.

        Returns:
            list[File]: List of File objects representing uploaded files
        """
        files = self._google_client.files.list()
        return list(files)  # Convert iterator to list
