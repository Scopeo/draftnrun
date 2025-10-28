"""
Dummy LLM service that simulates embedding and chat completion endpoints for testing purposes.
Generates fixed 1536-dimensional vectors with values of 0.1 and always returns
"this is the dummy llm speaking" for chat completions.
"""

import asyncio
from typing import List, Union, Optional, Dict, Any
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn


@dataclass
class EmbeddingData:
    """Mock embedding data structure that mimics OpenAI's embedding response."""

    embedding: List[float]
    index: int = 0


# Pydantic models for API requests/responses
class EmbeddingRequest(BaseModel):
    """Request model for embedding API."""

    model: str = "dummy-embedding:latest"
    input: Union[str, List[str]]
    encoding_format: str = "float"


class EmbeddingObject(BaseModel):
    """Individual embedding object."""

    object: str = "embedding"
    index: int
    embedding: List[float]


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    """Response model for embedding API."""

    object: str = "list"
    data: List[EmbeddingObject]
    model: str
    usage: Usage


# Chat completion models
class ChatMessage(BaseModel):
    """Individual chat message."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Request model for chat completion API."""

    model: str = "dummy-chat"
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = "auto"


class ChatChoice(BaseModel):
    """Individual chat completion choice."""

    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class ChatUsage(BaseModel):
    """Token usage information for chat completions."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """Response model for chat completion API."""

    id: str = "dummy-chat-completion"
    object: str = "chat.completion"
    created: int = 1677610602
    model: str
    choices: List[ChatChoice]
    usage: ChatUsage


class DummyEmbeddingService:
    """
    Dummy embedding service that generates fixed 1536-dimensional vectors.
    Each vector contains values of 0.1 for all dimensions.
    """

    def __init__(self, embedding_size: int = 1536):
        self.embedding_size = embedding_size
        # Pre-generate a fixed vector of 0.1 values
        self._fixed_vector = [0.1] * embedding_size

    def embed_text(self, text: str) -> List[EmbeddingData]:
        """
        Synchronous method to generate embeddings.

        Args:
            text: Input text to embed

        Returns:
            List of EmbeddingData objects containing the fixed vector
        """
        return asyncio.run(self.embed_text_async(text))

    async def embed_text_async(self, text: str) -> List[EmbeddingData]:
        """
        Asynchronous method to generate embeddings.

        Args:
            text: Input text to embed

        Returns:
            List of EmbeddingData objects containing the fixed vector
        """
        # Simulate some processing time
        await asyncio.sleep(0.01)

        # Return the fixed vector wrapped in EmbeddingData
        return [EmbeddingData(embedding=self._fixed_vector.copy())]

    def embed_texts(self, texts: List[str]) -> List[EmbeddingData]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed

        Returns:
            List of EmbeddingData objects, one for each input text
        """
        return asyncio.run(self.embed_texts_async(texts))

    async def embed_texts_async(self, texts: List[str]) -> List[EmbeddingData]:
        """
        Asynchronous method to generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed

        Returns:
            List of EmbeddingData objects, one for each input text
        """
        # Simulate some processing time
        await asyncio.sleep(0.01)

        # Return the fixed vector for each input text
        return [EmbeddingData(embedding=self._fixed_vector.copy()) for _ in texts]


class DummyChatCompletionService:
    """
    Dummy chat completion service that always returns "this is the dummy llm speaking".
    """

    def __init__(self):
        self.dummy_response = "this is the dummy llm speaking"

    def complete(self, messages: Union[str, List[Dict[str, str]]], **kwargs) -> str:
        """
        Synchronous method to generate chat completion.

        Args:
            messages: Input messages (string or list of message dicts)
            **kwargs: Additional parameters (ignored)

        Returns:
            Always returns "this is the dummy llm speaking"
        """
        return asyncio.run(self.complete_async(messages, **kwargs))

    async def complete_async(self, messages: Union[str, List[Dict[str, str]]], **kwargs) -> str:
        """
        Asynchronous method to generate chat completion.

        Args:
            messages: Input messages (string or list of message dicts)
            **kwargs: Additional parameters (ignored)

        Returns:
            Always returns "this is the dummy llm speaking"
        """
        # Simulate some processing time
        await asyncio.sleep(0.01)

        return self.dummy_response

    def function_call(self, messages: Union[str, List[Dict[str, str]]], **kwargs) -> Dict[str, Any]:
        """
        Simulate function calling - returns a mock ChatCompletion response.

        Args:
            messages: Input messages (string or list of message dicts)
            **kwargs: Additional parameters (ignored)

        Returns:
            Mock ChatCompletion response
        """
        return asyncio.run(self.function_call_async(messages, **kwargs))

    async def function_call_async(self, messages: Union[str, List[Dict[str, str]]], **kwargs) -> Dict[str, Any]:
        """
        Asynchronous function calling simulation.

        Args:
            messages: Input messages (string or list of message dicts)
            **kwargs: Additional parameters (ignored)

        Returns:
            Mock ChatCompletion response
        """
        # Simulate some processing time
        await asyncio.sleep(0.01)

        # Calculate token usage (simple word count)
        if isinstance(messages, str):
            prompt_tokens = len(messages.split())
        else:
            prompt_tokens = sum(len(msg.get("content", "").split()) for msg in messages)

        completion_tokens = len(self.dummy_response.split())
        total_tokens = prompt_tokens + completion_tokens

        return {
            "id": "dummy-chat-completion",
            "object": "chat.completion",
            "created": 1677610602,
            "model": kwargs.get("model", "dummy-chat"),
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": self.dummy_response}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }


class DummyEmbeddingEndpoint:
    """
    HTTP endpoint simulator for embedding API.
    Mimics OpenAI's embedding API structure.
    """

    def __init__(self, embedding_size: int = 1536):
        self.embedding_service = DummyEmbeddingService(embedding_size)

    async def create_embeddings(
        self, model: str = "dummy-embedding", input: Union[str, List[str]] = None, **kwargs
    ) -> dict:
        """
        Simulate OpenAI's embeddings.create() method.

        Args:
            model: Model name (ignored in dummy implementation)
            input: Text or list of texts to embed
            **kwargs: Additional parameters (ignored)

        Returns:
            Dictionary mimicking OpenAI's embedding response format
        """
        if input is None:
            raise ValueError("Input text is required")

        # Handle both single string and list of strings
        if isinstance(input, str):
            texts = [input]
        else:
            texts = input

        # Generate embeddings
        embedding_data = await self.embedding_service.embed_texts_async(texts)

        # Format response to match OpenAI's structure
        response = {
            "object": "list",
            "data": [
                {"object": "embedding", "index": i, "embedding": data.embedding}
                for i, data in enumerate(embedding_data)
            ],
            "model": model,
            "usage": {
                "prompt_tokens": sum(len(text.split()) for text in texts),
                "total_tokens": sum(len(text.split()) for text in texts),
            },
        }

        return response


class DummyChatCompletionEndpoint:
    """
    HTTP endpoint simulator for chat completion API.
    Mimics OpenAI's chat completion API structure.
    """

    def __init__(self):
        self.chat_service = DummyChatCompletionService()

    async def create_chat_completion(
        self, model: str = "dummy-chat", messages: List[Dict[str, str]] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Simulate OpenAI's chat.completions.create() method.

        Args:
            model: Model name (ignored in dummy implementation)
            messages: List of chat messages
            **kwargs: Additional parameters (ignored)

        Returns:
            Dictionary mimicking OpenAI's chat completion response format
        """
        if messages is None:
            raise ValueError("Messages are required")

        # Generate completion
        response = await self.chat_service.function_call_async(messages, model=model, **kwargs)

        return response


# Example usage and testing
async def main():
    """Example usage of the dummy embedding and chat completion services."""

    # Create dummy services
    embedding_service = DummyEmbeddingService(embedding_size=1536)
    embedding_endpoint = DummyEmbeddingEndpoint(embedding_size=1536)
    chat_service = DummyChatCompletionService()
    chat_endpoint = DummyChatCompletionEndpoint()

    # Test single text embedding
    print("Testing single text embedding:")
    text = "Hello, world!"
    result = await embedding_service.embed_text_async(text)
    print(f"Input: {text}")
    print(f"Embedding dimension: {len(result[0].embedding)}")
    print(f"First 5 values: {result[0].embedding[:5]}")
    print(f"All values are 0.1: {all(v == 0.1 for v in result[0].embedding)}")
    print()

    # Test multiple texts embedding
    print("Testing multiple texts embedding:")
    texts = ["Hello", "World", "Test"]
    results = await embedding_service.embed_texts_async(texts)
    print(f"Input texts: {texts}")
    print(f"Number of embeddings: {len(results)}")
    print(f"Each embedding dimension: {len(results[0].embedding)}")
    print()

    # Test endpoint simulation
    print("Testing embedding endpoint simulation:")
    embedding_response = await embedding_endpoint.create_embeddings(
        model="text-embedding-ada-002", input="This is a test sentence."
    )
    print(f"Response structure: {list(embedding_response.keys())}")
    print(f"Number of embeddings: {len(embedding_response['data'])}")
    print(f"First embedding dimension: {len(embedding_response['data'][0]['embedding'])}")
    print(f"Usage info: {embedding_response['usage']}")
    print()

    # Test chat completion service
    print("Testing chat completion service:")
    messages = [{"role": "user", "content": "Hello, how are you?"}]
    chat_result = await chat_service.complete_async(messages)
    print(f"Input messages: {messages}")
    print(f"Response: {chat_result}")
    print()

    # Test chat completion function call
    print("Testing chat completion function call:")
    function_call_result = await chat_service.function_call_async(messages)
    print(f"Function call response structure: {list(function_call_result.keys())}")
    print(f"Response content: {function_call_result['choices'][0]['message']['content']}")
    print(f"Usage info: {function_call_result['usage']}")
    print()

    # Test chat completion endpoint
    print("Testing chat completion endpoint simulation:")
    chat_endpoint_response = await chat_endpoint.create_chat_completion(model="dummy-chat", messages=messages)
    print(f"Endpoint response structure: {list(chat_endpoint_response.keys())}")
    print(f"Response content: {chat_endpoint_response['choices'][0]['message']['content']}")
    print(f"Usage info: {chat_endpoint_response['usage']}")


# FastAPI application
app = FastAPI(
    title="Dummy LLM Service",
    description="A dummy LLM service that generates fixed 1536-dimensional vectors and chat completions",
    version="1.0.0",
)

# Global service instances
embedding_service = DummyEmbeddingService(embedding_size=1536)
chat_service = DummyChatCompletionService()


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Dummy LLM Service",
        "version": "1.0.0",
        "description": "Generates fixed 1536-dimensional vectors and chat completions",
        "endpoints": {
            "embeddings": "/v1/embeddings",
            "chat_completions": "/v1/chat/completions",
            "models": "/v1/models",
            "health": "/health",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "dummy-llm-service"}


@app.get("/v1/test")
async def test_endpoint():
    """Test endpoint to verify server is working."""
    return {"message": "Dummy LLM server is working", "status": "ok"}


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(request: EmbeddingRequest):
    """
    Create embeddings endpoint that mimics OpenAI's API.

    Args:
        request: EmbeddingRequest containing model, input text(s), and encoding format

    Returns:
        EmbeddingResponse with generated embeddings
    """
    try:
        print(f"Received embedding request: {request.model}")
        print(f"Input: {request.input}")

        # Handle both single string and list of strings
        if isinstance(request.input, str):
            texts = [request.input]
        else:
            texts = request.input

        # Generate embeddings
        embedding_data = await embedding_service.embed_texts_async(texts)

        # Create response objects
        embedding_objects = [
            EmbeddingObject(index=i, embedding=data.embedding) for i, data in enumerate(embedding_data)
        ]

        # Calculate token usage (simple word count)
        total_tokens = sum(len(text.split()) for text in texts)

        response = EmbeddingResponse(
            data=embedding_objects,
            model=request.model,
            usage=Usage(prompt_tokens=total_tokens, total_tokens=total_tokens),
        )

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embeddings: {str(e)}")


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(request: ChatCompletionRequest):
    """
    Create chat completion endpoint that mimics OpenAI's API.

    Args:
        request: ChatCompletionRequest containing model, messages, and other parameters

    Returns:
        ChatCompletionResponse with generated completion
    """
    try:
        print(f"Received chat completion request: {request.model}")
        print(f"Messages: {[msg.dict() for msg in request.messages]}")

        # Convert Pydantic messages to dict format
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Generate completion
        response = await chat_service.function_call_async(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            stream=request.stream,
            tools=request.tools,
            tool_choice=request.tool_choice,
        )

        # Convert to Pydantic response
        choices = [
            ChatChoice(
                index=choice["index"],
                message=ChatMessage(role=choice["message"]["role"], content=choice["message"]["content"]),
                finish_reason=choice["finish_reason"],
            )
            for choice in response["choices"]
        ]

        usage = ChatUsage(
            prompt_tokens=response["usage"]["prompt_tokens"],
            completion_tokens=response["usage"]["completion_tokens"],
            total_tokens=response["usage"]["total_tokens"],
        )

        return ChatCompletionResponse(
            id=response["id"],
            object=response["object"],
            created=response["created"],
            model=response["model"],
            choices=choices,
            usage=usage,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating chat completion: {str(e)}")


@app.get("/v1/models")
async def list_models():
    """List available models endpoint."""
    return {
        "object": "list",
        "data": [
            {
                "id": "dummy-embedding:latest",
                "object": "model",
                "created": 1677610602,
                "owned_by": "dummy-service",
                "permission": [],
                "root": "dummy-embedding:latest",
                "parent": None,
            },
            {
                "id": "dummy-chat",
                "object": "model",
                "created": 1677610602,
                "owned_by": "dummy-service",
                "permission": [],
                "root": "dummy-chat",
                "parent": None,
            },
        ],
    }


def start_server(host: str = "0.0.0.0", port: int = 8081):
    """Start the uvicorn server."""
    print(f"Starting Dummy LLM Service on http://{host}:{port}")
    print(f"API Documentation: http://{host}:{port}/docs")
    print(f"Health Check: http://{host}:{port}/health")
    print(f"Embeddings Endpoint: http://{host}:{port}/v1/embeddings")
    print(f"Chat Completions Endpoint: http://{host}:{port}/v1/chat/completions")
    print(f"Models Endpoint: http://{host}:{port}/v1/models")
    print()
    print("Custom Models Configuration:")
    print("Provider: dummy-llm")
    print("Base URL: http://localhost:8081/v1/")
    print("API Key: dummy-api-key")
    print("Available Models:")
    print("  - dummy-chat (completion)")
    print("  - dummy-embedding:latest (embedding)")
    print()
    print("Configuration file: dummy_llm_models.json")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Run the example usage
        asyncio.run(main())
    else:
        # Start the server by default
        start_server()
