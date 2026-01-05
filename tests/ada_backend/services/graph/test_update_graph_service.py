"""
Tests for graph update service - specifically testing draft mode validation.
Tests ensure that only draft versions (env='draft' AND tag_version=null) can be modified.

NOTE: These tests require PostgreSQL due to regex constraints in the GraphRunner model.
When the test suite is migrated to PostgreSQL, these tests will work automatically.
For now, they are marked as integration tests.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateSchema
from ada_backend.services.graph.update_graph_service import (
    update_graph_service,
    validate_graph_is_draft,
)

# Mark all tests in this module as integration tests requiring PostgreSQL
pytestmark = pytest.mark.skip(
    reason="Tests require PostgreSQL (SQLite doesn't support regex constraints). "
    "Run with PostgreSQL test database or enable when test suite is migrated to PostgreSQL."
)


@pytest.fixture
def test_organization(ada_backend_mock_session: Session):
    """Create a test organization."""
    return uuid.uuid4()


@pytest.fixture
def test_project(ada_backend_mock_session: Session, test_organization):
    """Create a test project."""
    project_id = uuid.uuid4()
    project = db.WorkflowProject(
        id=project_id,
        name="Test Project",
        description="Test project for graph validation",
        organization_id=test_organization,
        type=db.ProjectType.WORKFLOW,
    )
    ada_backend_mock_session.add(project)
    ada_backend_mock_session.commit()
    return project


@pytest.fixture
def draft_graph_runner(ada_backend_mock_session: Session, test_project):
    """
    Create a draft graph runner (env='draft', tag_version=null).
    This should be the only editable version.
    """
    graph_runner_id = uuid.uuid4()
    graph_runner = db.GraphRunner(
        id=graph_runner_id,
        tag_version=None,  # Draft has no tag
    )
    ada_backend_mock_session.add(graph_runner)
    ada_backend_mock_session.flush()

    # Bind to project with DRAFT environment
    binding = db.ProjectEnvironmentBinding(
        project_id=test_project.id,
        graph_runner_id=graph_runner_id,
        environment=db.EnvType.DRAFT,
    )
    ada_backend_mock_session.add(binding)
    ada_backend_mock_session.commit()

    return graph_runner


@pytest.fixture
def production_graph_runner(ada_backend_mock_session: Session, test_project):
    """
    Create a production graph runner (env='production', tag_version='v1.0.0').
    This should be read-only.
    """
    graph_runner_id = uuid.uuid4()
    graph_runner = db.GraphRunner(
        id=graph_runner_id,
        tag_version="v1.0.0",  # Production has a tag
    )
    ada_backend_mock_session.add(graph_runner)
    ada_backend_mock_session.flush()

    # Bind to project with PRODUCTION environment
    binding = db.ProjectEnvironmentBinding(
        project_id=test_project.id,
        graph_runner_id=graph_runner_id,
        environment=db.EnvType.PRODUCTION,
    )
    ada_backend_mock_session.add(binding)
    ada_backend_mock_session.commit()

    return graph_runner


@pytest.fixture
def tagged_draft_graph_runner(ada_backend_mock_session: Session, test_project):
    """
    Create a draft graph runner with a tag (env='draft', tag_version='v0.1.0').
    This represents a historical draft version and should be read-only.
    """
    graph_runner_id = uuid.uuid4()
    graph_runner = db.GraphRunner(
        id=graph_runner_id,
        tag_version="v0.1.0",  # Has a tag even though env is draft
    )
    ada_backend_mock_session.add(graph_runner)
    ada_backend_mock_session.flush()

    # Bind to project with DRAFT environment but with a tag
    binding = db.ProjectEnvironmentBinding(
        project_id=test_project.id,
        graph_runner_id=graph_runner_id,
        environment=db.EnvType.DRAFT,
    )
    ada_backend_mock_session.add(binding)
    ada_backend_mock_session.commit()

    return graph_runner


@pytest.fixture
def simple_graph_payload():
    """
    Create a simple graph payload for testing updates.
    """
    component_instance_id = str(uuid.uuid4())
    return GraphUpdateSchema(
        component_instances=[
            {
                "is_agent": True,
                "is_protected": False,
                "function_callable": True,
                "can_use_function_calling": False,
                "tool_parameter_name": None,
                "subcomponents_info": [],
                "id": component_instance_id,
                "name": "Test Component",
                "ref": "",
                "is_start_node": True,
                "component_id": "7a039611-49b3-4bfd-b09b-c0f93edf3b79",  # LLM Call component
                "parameters": [
                    {
                        "value": "Test prompt",
                        "name": "prompt_template",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "Answer this question: {input}",
                        "ui_component": "Textarea",
                        "ui_component_properties": {},
                        "is_advanced": False,
                    }
                ],
                "tool_description": {
                    "name": "Test Tool",
                    "description": "Test Description",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
            }
        ],
        relationships=[],
        edges=[],
    )


class TestValidateGraphIsDraft:
    """
    Tests for the validate_graph_is_draft function.
    """

    def test_allows_draft_with_no_tag(self, ada_backend_mock_session: Session, draft_graph_runner):
        """
        Test that draft graphs with no tag_version are allowed to be modified.
        This is the ONLY case where modification should be allowed.
        """
        # Should not raise an exception
        validate_graph_is_draft(ada_backend_mock_session, draft_graph_runner.id)

    def test_rejects_production_graph(self, ada_backend_mock_session: Session, production_graph_runner):
        """
        Test that production graphs are rejected.
        """
        with pytest.raises(ValueError) as exc_info:
            validate_graph_is_draft(ada_backend_mock_session, production_graph_runner.id)

        error_message = str(exc_info.value)
        assert "only draft versions" in error_message.lower()
        assert "env='production'" in error_message or "production" in error_message.lower()
        assert "v1.0.0" in error_message

    def test_rejects_tagged_draft_graph(self, ada_backend_mock_session: Session, tagged_draft_graph_runner):
        """
        Test that draft graphs with a tag_version are rejected.
        Even though env='draft', the presence of tag_version makes it read-only.
        """
        with pytest.raises(ValueError) as exc_info:
            validate_graph_is_draft(ada_backend_mock_session, tagged_draft_graph_runner.id)

        error_message = str(exc_info.value)
        assert "only draft versions" in error_message.lower()
        assert "v0.1.0" in error_message

    def test_allows_new_graph_without_binding(self, ada_backend_mock_session: Session):
        """
        Test that new graphs (without environment binding) are allowed.
        This is the creation case.
        """
        new_graph_id = uuid.uuid4()
        new_graph = db.GraphRunner(id=new_graph_id, tag_version=None)
        ada_backend_mock_session.add(new_graph)
        ada_backend_mock_session.commit()

        # Should not raise an exception for new graphs
        validate_graph_is_draft(ada_backend_mock_session, new_graph_id)

    def test_raises_error_for_nonexistent_graph(self, ada_backend_mock_session: Session):
        """
        Test that appropriate error is raised for non-existent graph.
        """
        non_existent_id = uuid.uuid4()

        with pytest.raises(ValueError) as exc_info:
            validate_graph_is_draft(ada_backend_mock_session, non_existent_id)

        # Should raise error about graph not being found (from get_env_relationship)
        # or about graph not existing
        error_message = str(exc_info.value)
        assert "not found" in error_message.lower()


class TestUpdateGraphServiceDraftValidation:
    """
    Integration tests for update_graph_service with draft validation.
    """

    @pytest.mark.asyncio
    async def test_allows_update_to_draft_graph(
        self,
        ada_backend_mock_session: Session,
        test_project,
        draft_graph_runner,
        simple_graph_payload,
    ):
        """
        Test that updates to draft graphs (env='draft', tag_version=null) are allowed.
        """
        result = await update_graph_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
            graph_project=simple_graph_payload,
        )

        # Should succeed without raising an exception
        assert result.graph_id == draft_graph_runner.id

    @pytest.mark.asyncio
    async def test_rejects_update_to_production_graph(
        self,
        ada_backend_mock_session: Session,
        test_project,
        production_graph_runner,
        simple_graph_payload,
    ):
        """
        Test that updates to production graphs are rejected.
        """
        with pytest.raises(ValueError) as exc_info:
            await update_graph_service(
                session=ada_backend_mock_session,
                graph_runner_id=production_graph_runner.id,
                project_id=test_project.id,
                graph_project=simple_graph_payload,
            )

        error_message = str(exc_info.value)
        assert "only draft versions" in error_message.lower()
        assert "production" in error_message.lower() or "env='production'" in error_message

    @pytest.mark.asyncio
    async def test_rejects_update_to_tagged_draft_graph(
        self,
        ada_backend_mock_session: Session,
        test_project,
        tagged_draft_graph_runner,
        simple_graph_payload,
    ):
        """
        Test that updates to tagged draft graphs are rejected.
        """
        with pytest.raises(ValueError) as exc_info:
            await update_graph_service(
                session=ada_backend_mock_session,
                graph_runner_id=tagged_draft_graph_runner.id,
                project_id=test_project.id,
                graph_project=simple_graph_payload,
            )

        error_message = str(exc_info.value)
        assert "only draft versions" in error_message.lower()
        assert "v0.1.0" in error_message

    @pytest.mark.asyncio
    async def test_allows_creation_of_new_graph(
        self,
        ada_backend_mock_session: Session,
        test_project,
        simple_graph_payload,
    ):
        """
        Test that creating a new graph runner works (no validation error).
        """
        new_graph_runner_id = uuid.uuid4()

        result = await update_graph_service(
            session=ada_backend_mock_session,
            graph_runner_id=new_graph_runner_id,
            project_id=test_project.id,
            graph_project=simple_graph_payload,
        )

        # Should succeed and return the new graph_id
        assert result.graph_id == new_graph_runner_id

        # Verify it was created as DRAFT
        binding = (
            ada_backend_mock_session.query(db.ProjectEnvironmentBinding)
            .filter(db.ProjectEnvironmentBinding.graph_runner_id == new_graph_runner_id)
            .first()
        )
        assert binding is not None
        assert binding.environment == db.EnvType.DRAFT


class TestDraftValidationErrorMessages:
    """
    Tests to ensure error messages are clear and helpful.
    """

    def test_error_message_includes_current_state(self, ada_backend_mock_session: Session, production_graph_runner):
        """
        Test that error messages include the current state of the graph.
        """
        with pytest.raises(ValueError) as exc_info:
            validate_graph_is_draft(ada_backend_mock_session, production_graph_runner.id)

        error_message = str(exc_info.value)

        # Should include current environment
        assert "production" in error_message.lower()

        # Should include current tag_version
        assert "v1.0.0" in error_message

        # Should tell user what to do
        assert "switch to the draft version" in error_message.lower()

    def test_error_message_explains_requirement(self, ada_backend_mock_session: Session, tagged_draft_graph_runner):
        """
        Test that error messages explain the requirement clearly.
        """
        with pytest.raises(ValueError) as exc_info:
            validate_graph_is_draft(ada_backend_mock_session, tagged_draft_graph_runner.id)

        error_message = str(exc_info.value)

        # Should explain the requirement
        assert "env='draft' and tag_version=null" in error_message.lower()

        # Should include what's wrong
        assert "v0.1.0" in error_message  # Current tag_version
