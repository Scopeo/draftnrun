"""
Tests for endpoint_polling cron entrypoint.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from ada_backend.services.cron.entries.endpoint_polling import (
    EndpointPollingUserPayload,
    EndpointPollingExecutionPayload,
    validate_registration,
    validate_execution,
    execute,
    _extract_ids_from_response,
    _extract_ids_and_filter_values_from_response,
)
from ada_backend.services.cron.entries.agent_inference import (
    AgentInferenceUserPayload,
    AgentInferenceExecutionPayload,
)
from ada_backend.services.cron.errors import CronValidationError
from ada_backend.database.models import DataSource, EnvType, Project, EndpointPollingHistory


@pytest.fixture
def mock_source():
    """Create a mock DataSource."""
    source = Mock(spec=DataSource)
    source.id = uuid4()
    source.organization_id = uuid4()
    source.database_schema = "test_schema"
    source.database_table_name = "test_table"
    return source


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock()
    return session


@pytest.fixture
def sample_workflow_input(mock_source):
    """Create a sample workflow input for testing."""
    return AgentInferenceUserPayload(
        project_id=uuid4(),
        env=EnvType.PRODUCTION,
        input_data={"messages": [{"role": "user", "content": "Test message"}]},
    )


@pytest.fixture
def sample_agent_inference_execution_payload(mock_source):
    """Create a sample agent inference execution payload for testing."""
    return AgentInferenceExecutionPayload(
        project_id=uuid4(),
        env=EnvType.PRODUCTION,
        input_data={"messages": [{"role": "user", "content": "Test message"}]},
        organization_id=mock_source.organization_id,
        created_by=uuid4(),
    )


@pytest.fixture
def sample_endpoint_response():
    """Sample API response with IDs."""
    return {
        "data": [
            {"id": "1", "status": "pending", "priority": "low"},
            {"id": "2", "status": "processing", "priority": "high"},
            {"id": "3", "status": "processing", "priority": "high"},
            {"id": "4", "status": "completed", "priority": "medium"},
        ]
    }


class TestExtractIdsFromResponse:
    """Tests for ID extraction from API responses."""

    def test_extract_simple_id(self):
        """Test extracting a simple ID field."""
        data = {"id": "123"}
        result = _extract_ids_from_response(data, "id")
        assert result == {"123"}

    def test_extract_ids_from_array(self):
        """Test extracting IDs from an array."""
        data = {
            "items": [
                {"id": "1", "name": "item1"},
                {"id": "2", "name": "item2"},
            ]
        }
        result = _extract_ids_from_response(data, "items[].id")
        assert result == {"1", "2"}

    def test_extract_ids_with_nested_path(self):
        """Test extracting IDs with nested path."""
        data = {
            "response": {
                "data": [
                    {"id": "1"},
                    {"id": "2"},
                ]
            }
        }
        result = _extract_ids_from_response(data, "response.data[].id")
        assert result == {"1", "2"}

    def test_extract_ids_invalid_path(self):
        """Test that invalid path raises error."""
        data = {"id": "123"}
        with pytest.raises(ValueError, match="not found in response"):
            _extract_ids_from_response(data, "invalid_path")


class TestExtractIdsAndFilterValues:
    """Tests for extracting IDs with filter values."""

    def test_extract_with_single_filter(self, sample_endpoint_response):
        """Test extracting IDs with a single filter field."""
        result = _extract_ids_and_filter_values_from_response(sample_endpoint_response, "data[].id", ["data[].status"])

        assert "1" in result
        assert "2" in result
        assert "3" in result
        assert "4" in result
        assert result["1"]["filter_values"]["data[].status"] == "pending"
        assert result["2"]["filter_values"]["data[].status"] == "processing"
        assert result["3"]["filter_values"]["data[].status"] == "processing"

    def test_extract_with_multiple_filters(self, sample_endpoint_response):
        """Test extracting IDs with multiple filter fields."""
        result = _extract_ids_and_filter_values_from_response(
            sample_endpoint_response,
            "data[].id",
            ["data[].status", "data[].priority"],
        )

        assert "2" in result
        assert result["2"]["filter_values"]["data[].status"] == "processing"
        assert result["2"]["filter_values"]["data[].priority"] == "high"

        assert "3" in result
        assert result["3"]["filter_values"]["data[].status"] == "processing"
        assert result["3"]["filter_values"]["data[].priority"] == "high"

    def test_extract_with_missing_filter_field(self):
        """Test extraction when filter field is missing."""
        data = {
            "data": [
                {"id": "1", "status": "pending"},
                {"id": "2"},  # Missing status
            ]
        }
        result = _extract_ids_and_filter_values_from_response(data, "data[].id", ["data[].status"])

        assert "1" in result
        assert "2" in result
        assert result["1"]["filter_values"]["data[].status"] == "pending"
        assert result["2"]["filter_values"]["data[].status"] is None


class TestValidateRegistration:
    """Tests for registration validation."""

    def test_validate_success(self, mock_db_session, sample_endpoint_response):
        """Test successful validation."""
        from ada_backend.database.models import Project

        project_id = uuid4()
        organization_id = uuid4()

        mock_project = Mock(spec=Project)
        mock_project.organization_id = organization_id

        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.httpx.Client") as mock_client_class,
            patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project),
        ):
            mock_response = Mock()
            mock_response.json.return_value = sample_endpoint_response
            mock_response.raise_for_status = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}

            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            user_input = EndpointPollingUserPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                workflow_input=AgentInferenceUserPayload(
                    project_id=project_id,
                    env=EnvType.PRODUCTION,
                    input_data={"messages": [{"role": "user", "content": "Test"}]},
                ),
            )

            user_id = uuid4()

            result = validate_registration(
                user_input,
                organization_id,
                user_id,
                db=mock_db_session,
            )

            assert isinstance(result, EndpointPollingExecutionPayload)
            assert result.workflow_input.organization_id == organization_id
            assert result.tracking_field_path == "data[].id"
            mock_client.get.assert_called_once()

    def test_validate_with_filter_fields(self, mock_db_session, sample_endpoint_response):
        """Test validation with filter fields."""
        from ada_backend.database.models import Project

        project_id = uuid4()
        organization_id = uuid4()

        mock_project = Mock(spec=Project)
        mock_project.organization_id = organization_id

        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.httpx.Client") as mock_client_class,
            patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project),
        ):
            mock_response = Mock()
            mock_response.json.return_value = sample_endpoint_response
            mock_response.raise_for_status = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}

            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            user_input = EndpointPollingUserPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                filter_fields={"data[].status": "processing"},
                workflow_input=AgentInferenceUserPayload(
                    project_id=project_id,
                    env=EnvType.PRODUCTION,
                    input_data={"messages": [{"role": "user", "content": "Test"}]},
                ),
            )

            user_id = uuid4()

            result = validate_registration(
                user_input,
                organization_id,
                user_id,
                db=mock_db_session,
            )

            assert result.filter_fields == {"data[].status": "processing"}

    def test_validate_invalid_endpoint_url(self, mock_db_session):
        """Test validation fails with unreachable endpoint."""
        from ada_backend.database.models import Project

        project_id = uuid4()
        organization_id = uuid4()

        mock_project = Mock(spec=Project)
        mock_project.organization_id = organization_id

        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.httpx.Client") as mock_client_class,
            patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project),
        ):
            import httpx

            mock_client = Mock()
            # httpx.ConnectError requires a request parameter, so we'll use a mock request
            mock_request = Mock()
            mock_client.get.side_effect = httpx.ConnectError("Connection failed", request=mock_request)
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            user_input = EndpointPollingUserPayload(
                endpoint_url="https://invalid-endpoint.example.com/items",
                tracking_field_path="data[].id",
                workflow_input=AgentInferenceUserPayload(
                    project_id=project_id,
                    env=EnvType.PRODUCTION,
                    input_data={"messages": [{"role": "user", "content": "Test"}]},
                ),
            )

            user_id = uuid4()

            with pytest.raises(CronValidationError, match="Failed to connect to endpoint"):
                validate_registration(
                    user_input,
                    organization_id,
                    user_id,
                    db=mock_db_session,
                )

    def test_validate_invalid_tracking_path(self, mock_db_session, sample_endpoint_response):
        """Test validation fails with invalid tracking field path."""
        from ada_backend.database.models import Project

        project_id = uuid4()
        organization_id = uuid4()

        mock_project = Mock(spec=Project)
        mock_project.organization_id = organization_id

        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.httpx.Client") as mock_client_class,
            patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project),
        ):
            mock_response = Mock()
            mock_response.json.return_value = sample_endpoint_response
            mock_response.raise_for_status = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}

            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            user_input = EndpointPollingUserPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="invalid.path",
                workflow_input=AgentInferenceUserPayload(
                    project_id=project_id,
                    env=EnvType.PRODUCTION,
                    input_data={"messages": [{"role": "user", "content": "Test"}]},
                ),
            )

            user_id = uuid4()

            with pytest.raises(CronValidationError, match="Failed to extract IDs"):
                validate_registration(
                    user_input,
                    organization_id,
                    user_id,
                    db=mock_db_session,
                )

    def test_validate_invalid_json_response(self, mock_db_session):
        """Test validation fails with invalid JSON response."""
        from ada_backend.database.models import Project

        project_id = uuid4()
        organization_id = uuid4()

        mock_project = Mock(spec=Project)
        mock_project.organization_id = organization_id

        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.httpx.Client") as mock_client_class,
            patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project),
        ):
            import json

            mock_response = Mock()
            mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            mock_response.raise_for_status = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/html"}

            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            user_input = EndpointPollingUserPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                workflow_input=AgentInferenceUserPayload(
                    project_id=project_id,
                    env=EnvType.PRODUCTION,
                    input_data={"messages": [{"role": "user", "content": "Test"}]},
                ),
            )

            user_id = uuid4()

            with pytest.raises(CronValidationError, match="returned invalid JSON"):
                validate_registration(
                    user_input,
                    organization_id,
                    user_id,
                    db=mock_db_session,
                )

    def test_validate_filter_fields_without_array_notation(self, mock_db_session):
        """Test validation fails when filter_fields used without array notation."""

        project_id = uuid4()
        organization_id = uuid4()

        mock_project = Mock(spec=Project)
        mock_project.organization_id = organization_id

        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.httpx.Client") as mock_client_class,
            patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project),
        ):
            mock_response = Mock()
            mock_response.json.return_value = {"id": "123"}
            mock_response.raise_for_status = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}

            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            user_input = EndpointPollingUserPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="id",
                filter_fields={"status": "processing"},
                workflow_input=AgentInferenceUserPayload(
                    project_id=project_id,
                    env=EnvType.PRODUCTION,
                    input_data={"messages": [{"role": "user", "content": "Test"}]},
                ),
            )

            user_id = uuid4()

            with pytest.raises(
                CronValidationError,
                match="filter_fields can only be used when tracking_field_path uses array notation",
            ):
                validate_registration(
                    user_input,
                    organization_id,
                    user_id,
                    db=mock_db_session,
                )

    def test_validate_http_error(self, mock_db_session):
        """Test validation fails with HTTP error status."""

        project_id = uuid4()
        organization_id = uuid4()

        mock_project = Mock(spec=Project)
        mock_project.organization_id = organization_id

        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.httpx.Client") as mock_client_class,
            patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project),
        ):
            import httpx

            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found", request=Mock(), response=mock_response
            )

            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            user_input = EndpointPollingUserPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                workflow_input=AgentInferenceUserPayload(
                    project_id=project_id,
                    env=EnvType.PRODUCTION,
                    input_data={"messages": [{"role": "user", "content": "Test"}]},
                ),
            )

            user_id = uuid4()

            with pytest.raises(CronValidationError, match="returned HTTP 404"):
                validate_registration(
                    user_input,
                    organization_id,
                    user_id,
                    db=mock_db_session,
                )


class TestValidateExecution:
    """Tests for execution validation."""

    def test_validate_execution_success(self, mock_db_session, mock_source, sample_agent_inference_execution_payload):
        """Test successful execution validation."""

        mock_project = Mock(spec=Project)
        mock_project.organization_id = sample_agent_inference_execution_payload.organization_id

        with patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project):
            payload = EndpointPollingExecutionPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                filter_fields=None,
                headers=None,
                timeout=30,
                workflow_input=sample_agent_inference_execution_payload,
            )

            # Should not raise
            validate_execution(payload, db=mock_db_session)

    def test_validate_execution_succeeds_when_source_exists(
        self, mock_db_session, mock_source, sample_agent_inference_execution_payload
    ):
        """Test execution validation succeeds when source exists."""

        mock_project = Mock(spec=Project)
        mock_project.organization_id = sample_agent_inference_execution_payload.organization_id

        with patch("ada_backend.services.cron.entries.agent_inference.get_project", return_value=mock_project):
            payload = EndpointPollingExecutionPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                filter_fields=None,
                headers=None,
                timeout=30,
                workflow_input=sample_agent_inference_execution_payload,
            )

            # Should not raise
            validate_execution(payload, db=mock_db_session)


class TestExecute:
    """Tests for the execute function."""

    @pytest.fixture
    def mock_httpx_client(self, sample_endpoint_response):
        """Mock httpx client for API calls."""
        with patch("ada_backend.services.cron.entries.endpoint_polling.httpx") as mock_httpx:
            mock_response = Mock()
            mock_response.json.return_value = sample_endpoint_response
            mock_response.raise_for_status = Mock()

            async def mock_get(*args, **kwargs):
                return mock_response

            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_httpx.AsyncClient.return_value = mock_client

            yield mock_client

    @pytest.mark.asyncio
    async def test_execute_simple_id_extraction(
        self, mock_db_session, mock_source, mock_httpx_client, sample_agent_inference_execution_payload
    ):
        """Test basic execution without filter fields."""
        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.get_tracked_values_history") as mock_get_history,
            patch("ada_backend.services.cron.entries.endpoint_polling.create_tracked_values_bulk") as _,
        ):
            mock_get_history.return_value = []

            payload = EndpointPollingExecutionPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                filter_fields=None,
                headers=None,
                timeout=30,
                workflow_input=sample_agent_inference_execution_payload,
            )

            result = await execute(payload, db=mock_db_session, cron_id=uuid4())

            assert "new_values" in result
            assert "total_polled_values" in result

    @pytest.mark.asyncio
    async def test_execute_with_filter_fields(
        self, mock_db_session, mock_source, mock_httpx_client, sample_agent_inference_execution_payload
    ):
        """Test execution with filter fields."""
        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.get_tracked_values_history") as mock_get_history,
            patch("ada_backend.services.cron.entries.endpoint_polling.create_tracked_values_bulk") as _,
        ):
            mock_get_history.return_value = []

            payload = EndpointPollingExecutionPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                filter_fields={"data[].status": "processing", "data[].priority": "high"},
                headers=None,
                timeout=30,
                workflow_input=sample_agent_inference_execution_payload,
            )

            result = await execute(payload, db=mock_db_session, cron_id=uuid4())

            assert "new_values" in result

    @pytest.mark.asyncio
    async def test_execute_with_previous_run_state(
        self, mock_db_session, mock_source, mock_httpx_client, sample_agent_inference_execution_payload
    ):
        """Test execution with previous run state to detect changes."""

        # Mock tracking history with previous state: item "2" and "3" were already tracked
        mock_history = [
            Mock(spec=EndpointPollingHistory, tracked_value="2"),
            Mock(spec=EndpointPollingHistory, tracked_value="3"),
        ]

        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.get_tracked_values_history") as mock_get_history,
            patch("ada_backend.services.cron.entries.endpoint_polling.create_tracked_values_bulk") as _,
        ):
            mock_get_history.return_value = mock_history

            payload = EndpointPollingExecutionPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                filter_fields={"data[].status": "processing", "data[].priority": "high"},
                headers=None,
                timeout=30,
                workflow_input=sample_agent_inference_execution_payload,
            )

            result = await execute(payload, db=mock_db_session, cron_id=uuid4())

            assert "new_values" in result

    @pytest.mark.asyncio
    async def test_execute_missing_ingestion_db_url(
        self, mock_db_session, mock_source, mock_httpx_client, sample_agent_inference_execution_payload
    ):
        """Test execution with missing database."""
        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.get_tracked_values_history") as mock_get_history,
            patch("ada_backend.services.cron.entries.endpoint_polling.create_tracked_values_bulk") as _,
        ):
            mock_get_history.return_value = []

            payload = EndpointPollingExecutionPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                filter_fields=None,
                headers=None,
                timeout=30,
                workflow_input=sample_agent_inference_execution_payload,
            )

            # Should not raise
            result = await execute(payload, db=mock_db_session, cron_id=uuid4())
            assert "new_values" in result

    @pytest.mark.asyncio
    async def test_execute_empty_ingestion_db(
        self, mock_db_session, mock_source, mock_httpx_client, sample_agent_inference_execution_payload
    ):
        """Test execution with empty history database."""
        with (
            patch("ada_backend.services.cron.entries.endpoint_polling.get_tracked_values_history") as mock_get_history,
            patch("ada_backend.services.cron.entries.endpoint_polling.create_tracked_values_bulk") as _,
        ):
            mock_get_history.return_value = []

            payload = EndpointPollingExecutionPayload(
                endpoint_url="https://api.example.com/items",
                tracking_field_path="data[].id",
                filter_fields=None,
                headers=None,
                timeout=30,
                workflow_input=sample_agent_inference_execution_payload,
            )

            result = await execute(payload, db=mock_db_session, cron_id=uuid4())

            assert result["total_stored_ids"] == 0
            # All endpoint IDs (1, 2, 3, 4) should be new
            assert len(result["new_values"]) == 4
            assert set(result["new_values"]) == {"1", "2", "3", "4"}
