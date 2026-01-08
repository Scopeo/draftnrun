"""
Tests for agent repository functions.
Testing the versioning features for agents with multiple graph runners.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db
from ada_backend.repositories.agent_repository import (
    fetch_agents_with_graph_runners_by_organization,
)


@pytest.fixture
def db_session():
    """Get a database session for testing."""
    session_gen = get_db()
    session = next(session_gen)
    yield session
    session.close()


@pytest.fixture
def test_organization(db_session: Session):
    """Create a test organization."""
    org_id = uuid.uuid4()
    return org_id


@pytest.fixture
def test_agent_with_versions(db_session: Session, test_organization):
    """
    Create a test agent with multiple graph runner versions.
    This simulates the versioning feature where agents can have draft, production versions.
    """
    # Create agent project
    agent_id = uuid.uuid4()
    agent = db.AgentProject(
        id=agent_id,
        name="Test AI Agent",
        description="Test agent for versioning",
        organization_id=test_organization,
        type=db.ProjectType.AGENT,
    )
    db_session.add(agent)
    db_session.flush()

    # Create multiple graph runners (versions)
    draft_graph_runner = db.GraphRunner(
        id=uuid.uuid4(),
        tag_version="v1.0.0-draft",
    )
    production_graph_runner = db.GraphRunner(
        id=uuid.uuid4(),
        tag_version="v1.0.0",
    )
    db_session.add(draft_graph_runner)
    db_session.add(production_graph_runner)
    db_session.flush()

    # Create environment bindings
    draft_binding = db.ProjectEnvironmentBinding(
        project_id=agent_id,
        graph_runner_id=draft_graph_runner.id,
        environment=db.EnvType.DRAFT,
    )
    production_binding = db.ProjectEnvironmentBinding(
        project_id=agent_id,
        graph_runner_id=production_graph_runner.id,
        environment=db.EnvType.PRODUCTION,
    )
    db_session.add(draft_binding)
    db_session.add(production_binding)
    db_session.commit()

    return {
        "agent": agent,
        "draft_graph_runner": draft_graph_runner,
        "production_graph_runner": production_graph_runner,
        "draft_binding": draft_binding,
        "production_binding": production_binding,
    }


def test_fetch_agents_with_graph_runners_returns_correct_structure(
    db_session: Session, test_agent_with_versions, test_organization
):
    """
    Test that fetch_agents_with_graph_runners_by_organization returns
    tuples of (agent, graph_runner, binding) as expected.
    """
    results = fetch_agents_with_graph_runners_by_organization(db_session, test_organization)

    # Should return list of tuples
    assert isinstance(results, list)
    assert len(results) == 2  # Two versions (draft + production)

    # Each result should have 3 elements (SQLAlchemy Row object)
    for result in results:
        assert len(result) == 3
        agent, graph_runner, binding = result

        # Verify types
        assert isinstance(agent, db.AgentProject)
        assert isinstance(graph_runner, db.GraphRunner)
        assert isinstance(binding, db.ProjectEnvironmentBinding)


def test_fetch_agents_includes_all_versions(db_session: Session, test_agent_with_versions, test_organization):
    """
    Test that all graph runner versions for an agent are returned.
    """
    results = fetch_agents_with_graph_runners_by_organization(db_session, test_organization)

    # Extract graph runner IDs from results
    graph_runner_ids = [result[1].id for result in results]

    # Should include both draft and production versions
    expected_draft_id = test_agent_with_versions["draft_graph_runner"].id
    expected_prod_id = test_agent_with_versions["production_graph_runner"].id

    assert expected_draft_id in graph_runner_ids
    assert expected_prod_id in graph_runner_ids


def test_fetch_agents_returns_correct_environment_bindings(
    db_session: Session, test_agent_with_versions, test_organization
):
    """
    Test that each graph runner is returned with its correct environment binding.
    """
    results = fetch_agents_with_graph_runners_by_organization(db_session, test_organization)

    # Build a map of graph_runner_id -> environment
    env_map = {result[1].id: result[2].environment for result in results}

    # Verify environments match
    draft_id = test_agent_with_versions["draft_graph_runner"].id
    prod_id = test_agent_with_versions["production_graph_runner"].id

    assert env_map[draft_id] == db.EnvType.DRAFT
    assert env_map[prod_id] == db.EnvType.PRODUCTION


def test_fetch_agents_returns_correct_tag_versions(db_session: Session, test_agent_with_versions, test_organization):
    """
    Test that tag_version is correctly included with each graph runner.
    """
    results = fetch_agents_with_graph_runners_by_organization(db_session, test_organization)

    # Build a map of graph_runner_id -> tag_version
    version_map = {result[1].id: result[1].tag_version for result in results}

    # Verify tag versions
    draft_id = test_agent_with_versions["draft_graph_runner"].id
    prod_id = test_agent_with_versions["production_graph_runner"].id

    assert version_map[draft_id] == "v1.0.0-draft"
    assert version_map[prod_id] == "v1.0.0"


def test_fetch_agents_orders_by_creation_date(db_session: Session, test_organization):
    """
    Test that results are ordered by agent creation date, then graph runner creation date.
    """
    # Create two agents with specific creation times
    agent1_id = uuid.uuid4()
    agent1 = db.AgentProject(
        id=agent1_id,
        name="Agent 1",
        organization_id=test_organization,
        type=db.ProjectType.AGENT,
    )
    db_session.add(agent1)
    db_session.flush()

    agent2_id = uuid.uuid4()
    agent2 = db.AgentProject(
        id=agent2_id,
        name="Agent 2",
        organization_id=test_organization,
        type=db.ProjectType.AGENT,
    )
    db_session.add(agent2)
    db_session.flush()

    # Create graph runners for each agent
    gr1 = db.GraphRunner(id=uuid.uuid4(), tag_version="v1")
    gr2 = db.GraphRunner(id=uuid.uuid4(), tag_version="v2")
    db_session.add_all([gr1, gr2])
    db_session.flush()

    # Create bindings
    binding1 = db.ProjectEnvironmentBinding(
        project_id=agent1_id,
        graph_runner_id=gr1.id,
        environment=db.EnvType.DRAFT,
    )
    binding2 = db.ProjectEnvironmentBinding(
        project_id=agent2_id,
        graph_runner_id=gr2.id,
        environment=db.EnvType.DRAFT,
    )
    db_session.add_all([binding1, binding2])
    db_session.commit()

    results = fetch_agents_with_graph_runners_by_organization(db_session, test_organization)

    # Verify ordering - should get agents in order they were created
    agent_ids = [result[0].id for result in results]

    # Agent1 was created first, should appear first in results
    first_agent_id = agent_ids[0]
    assert first_agent_id == agent1_id


def test_fetch_agents_empty_organization(db_session: Session):
    """
    Test that fetching agents for an organization with no agents returns empty list.
    """
    empty_org_id = uuid.uuid4()
    results = fetch_agents_with_graph_runners_by_organization(db_session, empty_org_id)

    assert isinstance(results, list)
    assert len(results) == 0


def test_fetch_agents_filters_by_organization(db_session: Session, test_agent_with_versions, test_organization):
    """
    Test that only agents from the specified organization are returned.
    """
    # Create an agent in a different organization
    other_org_id = uuid.uuid4()
    other_agent_id = uuid.uuid4()
    other_agent = db.AgentProject(
        id=other_agent_id,
        name="Other Org Agent",
        organization_id=other_org_id,
        type=db.ProjectType.AGENT,
    )
    db_session.add(other_agent)

    other_gr = db.GraphRunner(id=uuid.uuid4(), tag_version="v1")
    db_session.add(other_gr)
    db_session.flush()

    other_binding = db.ProjectEnvironmentBinding(
        project_id=other_agent_id,
        graph_runner_id=other_gr.id,
        environment=db.EnvType.DRAFT,
    )
    db_session.add(other_binding)
    db_session.commit()

    # Fetch agents for the test organization
    results = fetch_agents_with_graph_runners_by_organization(db_session, test_organization)

    # Should only get agents from test_organization
    agent_ids = [result[0].id for result in results]
    assert other_agent_id not in agent_ids
    assert test_agent_with_versions["agent"].id in agent_ids
