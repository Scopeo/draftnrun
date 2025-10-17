from fastapi.testclient import TestClient

from ada_backend.main import app

from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.trace_schema import RootTraceSpan, PaginatedRootTracesResponse
from ada_backend.scripts.get_supabase_token import get_user_jwt
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from settings import settings

client = TestClient(app)


def test_monitor_endpoint():
    trace_manager = TraceManager(project_name="ada-backend-test")
    set_trace_manager(trace_manager)
    project_id = "f7ddbfcb-6843-4ae9-a15b-40aa565b955b"  # graph test project

    token = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
    endpoint = f"/projects/{project_id}/draft/chat"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data = {"messages": [{"role": "user", "content": "Hello, how are you?"}]}
    response = client.post(endpoint, json=data, headers=headers)
    output = ChatResponse.model_validate(response.json())
    assert isinstance(output.message, str)
    assert output.error is None, f"Graph execution failed with error: {output.error}"
    assert isinstance(output.artifacts, dict)

    # Force flush the trace manager to ensure spans are exported
    trace_manager.force_flush()

    duration = 7
    url = f"/projects/{project_id}/traces?duration={duration}"
    response = client.get(url, headers=headers)

    assert response.status_code == 200

    # Validate the paginated response structure
    paginated_response = PaginatedRootTracesResponse.model_validate(response.json())

    # Check pagination metadata
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
