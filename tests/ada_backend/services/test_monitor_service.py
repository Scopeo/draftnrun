import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage

from ada_backend.database.models import CallType, EnvType
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.trace_schema import RootTraceSpan
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.services.trace_service import get_root_traces_by_project
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from tests.ada_backend.test_utils import GRAPH_TEST_PROJECT_ID


def create_mock_chat_completion(content: str = "Hello! I'm doing well, thank you for asking.") -> ChatCompletion:
    """Create a minimal mock ChatCompletion response."""
    return ChatCompletion(
        id="test-completion-id",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=content,
                    tool_calls=None,
                ),
                finish_reason="stop",
            )
        ],
        created=1234567890,
        model="gpt-4",
        object="chat.completion",
        usage=CompletionUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        ),
    )


@patch("engine.qdrant_service.QdrantService.retrieve_similar_chunks_async", new_callable=AsyncMock)
@patch("engine.llm_services.providers.openai_provider.OpenAIProvider.complete", new_callable=AsyncMock)
@patch(
    "engine.llm_services.providers.openai_provider.OpenAIProvider.function_call_without_structured_output",
    new_callable=AsyncMock,
)
@patch(
    "engine.llm_services.providers.openai_provider.OpenAIProvider.constrained_complete_with_json_schema",
    new_callable=AsyncMock,
)
def test_monitor_service(
    mock_constrained_complete,
    mock_function_call,
    mock_complete,
    mock_retrieve_chunks,
):
    """Test monitor service - chat execution and trace retrieval."""
    mock_retrieve_chunks.return_value = []
    mock_complete.return_value = ("Hello! I'm doing well, thank you for asking.", 10, 20, 30)
    mock_function_call.return_value = (create_mock_chat_completion(), 10, 20, 30)
    mock_constrained_complete.return_value = ('{"response": "test"}', 10, 20, 30)

    trace_manager = TraceManager(project_name="ada-backend-test")
    set_trace_manager(trace_manager)

    user_id = uuid4()

    with get_db_session() as session:
        data = {"messages": [{"role": "user", "content": "Hello, how are you?"}]}
        output = asyncio.run(
            run_env_agent(
                session=session,
                project_id=GRAPH_TEST_PROJECT_ID,
                env=EnvType.DRAFT,
                input_data=data,
                call_type=CallType.SANDBOX,
            )
        )
        assert isinstance(output.message, str)
        assert output.error is None, f"Graph execution failed with error: {output.error}"
        assert isinstance(output.artifacts, dict)

        # Force flush the trace manager to ensure spans are exported
        trace_manager.force_flush()

        duration = 7
        paginated_response = get_root_traces_by_project(
            user_id=user_id,
            project_id=GRAPH_TEST_PROJECT_ID,
            duration=duration,
        )

        # Validate the paginated response structure
        assert paginated_response.pagination.page >= 1
        assert paginated_response.pagination.size > 0
        assert paginated_response.pagination.total_items >= 0
        assert paginated_response.pagination.total_pages >= 0

        # Check traces list
        traces = paginated_response.traces
        assert len(traces) > 0
        assert isinstance(traces, list)

        # Validate each trace has all required RootTraceSpan fields
        keys_trace_span = list(RootTraceSpan.model_fields.keys())
        for trace in traces:
            trace_dict = trace.model_dump()
            assert all(key in trace_dict for key in keys_trace_span)
