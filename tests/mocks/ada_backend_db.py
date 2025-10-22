from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ada_backend.database import models as db
from ada_backend.database.models import Base
from settings import settings


@pytest.fixture(scope="function")
def test_db():
    """
    Connects to the PostgreSQL database for testing.
    Uses transactions for test isolation without affecting the actual database.
    """
    if not settings.ADA_DB_URL:
        raise ValueError("ADA_DB_URL is not configured. Please set it in credentials.env")

    engine = create_engine(settings.ADA_DB_URL, echo=False)

    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    yield engine, SessionLocal

    engine.dispose()


MOCK_UUIDS: dict[str, UUID] = {
    "project_1": uuid4(),
    "project_2": uuid4(),
    "project_secret_1": uuid4(),
    "project_secret_2": uuid4(),
    "component_1": uuid4(),
    "component_2": uuid4(),
    "component_3": uuid4(),
    "component_4": uuid4(),
    "component_5": uuid4(),
    "component_6": uuid4(),
    "tool_description_1": uuid4(),
    "tool_description_2": uuid4(),
    "component_instance_1": uuid4(),
    "component_instance_2": uuid4(),
    "component_instance_3": uuid4(),
    "component_instance_4": uuid4(),
    "component_instance_5": uuid4(),
    "component_instance_6": uuid4(),
}


def populate_ada_backend_db_with_mock_data(session: Session):
    """
    Populate the test database with mock data for ada_backend.
    """

    # --- Organization ---
    test_org_id = uuid4()

    # --- Projects ---
    project_1 = db.WorkflowProject(
        id=MOCK_UUIDS["project_1"],
        name="Project A",
        description="First test project.",
        type=db.ProjectType.WORKFLOW,
        organization_id=test_org_id,
    )
    project_2 = db.AgentProject(
        id=MOCK_UUIDS["project_2"],
        name="Project B",
        description="Second test project.",
        type=db.ProjectType.AGENT,
        organization_id=test_org_id,
    )
    session.add_all([project_1, project_2])
    session.commit()

    # --- Add Organization Secret ---
    project_secret_1 = db.OrganizationSecret(
        id=MOCK_UUIDS["project_secret_1"],
        organization_id=test_org_id,
        key="API_KEY",
    )
    project_secret_1.set_secret("super_secret_key")
    session.add(project_secret_1)
    session.commit()

    # --- Components ---
    component_1 = db.Component(
        id=MOCK_UUIDS["component_1"],
        name="TestMockCompletionService",
        description="Completion Service.",
    )
    component_2 = db.Component(
        id=MOCK_UUIDS["component_2"],
        name="TestMockSynthesizer",
        description="Synthesizer Component.",
    )
    component_3 = db.Component(
        id=MOCK_UUIDS["component_3"],
        name="TestMockRetriever",
        description="Retriever Component.",
    )
    component_4 = db.Component(
        id=MOCK_UUIDS["component_4"],
        name="TestMockReActAgent",
        description="ReAct framework agent.",
        is_agent=True,
    )
    component_5 = db.Component(
        id=MOCK_UUIDS["component_5"],
        name="TestMockRAGAgent",
        description="Retrieve and Generate Agent.",
        is_agent=True,
    )
    component_6 = db.Component(
        id=MOCK_UUIDS["component_6"],
        name="TestMockEmbeddingService",
        description="Embedding Service.",
    )
    session.add_all([component_1, component_2, component_3, component_4, component_5, component_6])
    session.commit()

    # --- Tool Descriptions ---
    tool_description_1 = db.ToolDescription(
        id=MOCK_UUIDS["tool_description_1"],
        name=f"TestMockTool1_{test_org_id.hex[:8]}",
        description="Mock tool description 1.",
        tool_properties={"prop1": "value1"},
        required_tool_properties={"req1": "value1"},
    )
    tool_description_2 = db.ToolDescription(
        id=MOCK_UUIDS["tool_description_2"],
        name=f"TestMockTool2_{test_org_id.hex[:8]}",
        description="Mock tool description 2.",
        tool_properties={"prop2": "value2"},
        required_tool_properties={"req2": "value2"},
    )
    session.add_all([tool_description_1, tool_description_2])
    session.commit()

    # --- Component Instances ---
    component_instance_1 = db.ComponentInstance(
        id=MOCK_UUIDS["component_instance_1"],
        component_id=component_1.id,
        ref="completion_service_a",
    )
    component_instance_2 = db.ComponentInstance(
        id=MOCK_UUIDS["component_instance_2"],
        component_id=component_2.id,
        ref="synthesizer_a",
    )
    component_instance_3 = db.ComponentInstance(
        id=MOCK_UUIDS["component_instance_3"],
        component_id=component_3.id,
        ref="retriever_b",
    )
    component_instance_4 = db.ComponentInstance(
        id=MOCK_UUIDS["component_instance_4"],
        component_id=component_4.id,
        ref="react_agent_a",
        tool_description_id=tool_description_1.id,
    )
    component_instance_5 = db.ComponentInstance(
        id=MOCK_UUIDS["component_instance_5"],
        component_id=component_5.id,
        ref="rag_agent_b",
        tool_description_id=tool_description_2.id,
    )
    component_instance_6 = db.ComponentInstance(
        id=MOCK_UUIDS["component_instance_6"],
        component_id=component_6.id,
        ref="embedding_service_a",
    )
    session.add_all(
        [
            component_instance_1,
            component_instance_2,
            component_instance_3,
            component_instance_4,
            component_instance_5,
            component_instance_6,
        ]
    )
    session.commit()

    # Skip BasicParameters and ComponentSubInputs - not needed for these tests
    # This speeds up test execution significantly


def populate_ada_backend_db_from_seed(session: Session):
    """
    Populate the test database with seed data.
    Import is done lazily to avoid loading weasyprint dependencies at module import time.
    """
    from ada_backend.database.seed_db import seed_db

    seed_db(session)


@pytest.fixture(scope="function")
def ada_backend_mock_session(test_db):
    """
    Provides a SQLAlchemy session for testing.
    Automatically rolls back changes after the test.
    """
    engine, SessionLocal = test_db  # Unpack the engine and session factory
    connection = engine.connect()
    transaction = connection.begin()
    _session = SessionLocal(bind=connection)

    populate_ada_backend_db_with_mock_data(_session)

    yield _session  # This is where the tests runs

    _session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def ada_backend_seed_session(test_db):
    """
    Provides a SQLAlchemy session for testing.
    Automatically rolls back changes after the test.
    """
    engine, SessionLocal = test_db
    connection = engine.connect()
    transaction = connection.begin()
    _session = SessionLocal(bind=connection)

    populate_ada_backend_db_from_seed(_session)

    yield _session

    _session.close()
    transaction.rollback()
    connection.close()
