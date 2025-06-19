from unittest.mock import MagicMock


class MockTraceManager:
    def __init__(
        self,
        project_name: str,
    ):
        self.project_id = "mock_project_id"
        self.organization_id = "mock_organization_id"
        self.organization_llm_providers = "mock_llm_providers"

    def start_span(self, *args, **kwargs):
        # Return a context manager that does nothing
        return MagicMock()
