from unittest.mock import MagicMock


class MockTraceManager:
    def __init__(
        self,
        project_name: str,
    ):
        self._project_id = "mock_project_id"

    @property
    def projet_id(self) -> str:
        return self._project_id

    @projet_id.setter
    def project_id(self, project_id: str):
        self._project_id = project_id

    def start_span(self, *args, **kwargs):
        # Return a context manager that does nothing
        return MagicMock()
