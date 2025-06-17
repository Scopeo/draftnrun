from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from ada_backend.main import app
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.trace_schema import TraceSpan
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

client = TestClient(app)


def test_monitor_endpoint():
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
    assert output.error is None or isinstance(output.error, str)
    assert isinstance(output.artifacts, dict)

    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.force_flush()

    duration = 7
    url = f"/projects/{project_id}/trace?duration={duration}"
    response = client.get(url, headers=headers)

    results = response.json()
    keys_trace_span = [field_name[0] for field_name in TraceSpan.model_fields.items()]

    assert response.status_code == 200
    assert len(results) > 0
    assert isinstance(results, list)
    assert all(isinstance(result, dict) for result in results)
    assert all(key in result for result in results for key in keys_trace_span)
