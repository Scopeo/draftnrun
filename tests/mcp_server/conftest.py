import pytest

# Stable fake UUIDs for tests — valid format so they pass native UUID validation.
FAKE_PROJECT_ID = "00000000-0000-4000-8000-000000000001"
FAKE_RUNNER_ID = "00000000-0000-4000-8000-000000000002"
FAKE_AGENT_ID = "00000000-0000-4000-8000-000000000003"
FAKE_RUN_ID = "00000000-0000-4000-8000-000000000004"
FAKE_ORG_ID = "00000000-0000-4000-8000-000000000005"
FAKE_SOURCE_ID = "00000000-0000-4000-8000-000000000006"
FAKE_DOC_ID = "00000000-0000-4000-8000-000000000007"
FAKE_KEY_ID = "00000000-0000-4000-8000-000000000008"
FAKE_CRON_ID = "00000000-0000-4000-8000-000000000009"
FAKE_CONN_ID = "00000000-0000-4000-8000-00000000000a"
FAKE_DATASET_ID = "00000000-0000-4000-8000-00000000000b"
FAKE_JUDGE_ID = "00000000-0000-4000-8000-00000000000c"
FAKE_TRACE_ID = "00000000-0000-4000-8000-00000000000d"
FAKE_VERSION_OUTPUT_ID = "00000000-0000-4000-8000-00000000000e"
FAKE_SET_ID = "00000000-0000-4000-8000-00000000000f"

# OTel-format trace ID (0x-prefixed hex, NOT a UUID).
FAKE_OTEL_TRACE_ID = "0x6d4e58f8ef17eae5436d8577814f6e60"


class FakeMCP:
    def __init__(self):
        self.tools = {}
        self.resources = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator

    def resource(self, uri, name=None, description=None):
        def decorator(func):
            self.resources[uri] = {"func": func, "name": name, "description": description}
            return func

        return decorator


@pytest.fixture
def fake_mcp():
    return FakeMCP()
