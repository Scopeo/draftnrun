from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from ada_backend.database.seed_db import seed_db
from ada_backend.database.models import Base, ParameterType
from ada_backend.database import models as db
from settings import settings
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy import text


@pytest.fixture(scope="function")
def test_db():
    """
    Provides a PostgreSQL database connection for testing.
    Requires ADA_TEST_DB_URL or ADA_DB_URL to be configured.
    """
    db_url = settings.ADA_TEST_DB_URL
    if not db_url:
        pytest.skip("ADA_TEST_DB_URL must be set to run PostgreSQL-backed database tests.")

    url = make_url(db_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("Database tests require a PostgreSQL URL (ADA_TEST_DB_URL / ADA_DB_URL).")

    engine = create_engine(db_url)
    created_additional_schemas: set[str] = set()
    required_schemas = {"scheduler", "quality_assurance"}
    try:
        schema_name = f"test_schema_{uuid4().hex}"
        with engine.connect() as connection:
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            for schema in required_schemas:
                exists = connection.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = :name"
                    ),
                    {"name": schema},
                ).fetchone()
                if not exists:
                    connection.execute(text(f"CREATE SCHEMA {schema}"))
                    created_additional_schemas.add(schema)
        engine.test_schema = schema_name
        with engine.connect() as connection:
            connection.execute(text(f"SET search_path TO {schema_name}"))
            Base.metadata.create_all(bind=connection)
    except OperationalError as exc:
        pytest.skip(f"Unable to connect to PostgreSQL database: {exc}")

    # Define a reusable session factory
    SessionLocal = sessionmaker(bind=engine)
    SessionLocal.test_schema = schema_name
    engine.created_test_schemas = created_additional_schemas

    yield engine, SessionLocal

    with engine.connect() as connection:
        connection.execute(text(f"SET search_path TO {schema_name}"))
        Base.metadata.drop_all(bind=connection)
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        for schema in getattr(engine, "created_test_schemas", set()):
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
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
    "tool_description_1": uuid4(),
    "tool_description_2": uuid4(),
    "component_instance_1": uuid4(),
    "component_instance_2": uuid4(),
    "component_instance_3": uuid4(),
    "component_instance_4": uuid4(),
    "component_instance_5": uuid4(),
}


def populate_ada_backend_db_with_mock_data(session: Session):
    """
    Populate the test database with mock data for ada_backend.
    """

    # --- Projects ---
    project_1 = db.Project(id=MOCK_UUIDS["project_1"], name="Project A", description="First test project.")
    project_2 = db.Project(id=MOCK_UUIDS["project_2"], name="Project B", description="Second test project.")
    session.add_all([project_1, project_2])
    session.commit()

    # --- Add Project Secret ---
    project_secret_1 = db.OrganizationSecret(
        id=MOCK_UUIDS["project_secret_1"],
        project_id=project_1.id,
        key="API_KEY",
    )
    project_secret_1.set_secret("super_secret_key")
    session.add(project_secret_1)
    session.commit()

    # --- Components ---
    component_1 = db.Component(
        id=MOCK_UUIDS["component_1"],
        name="CompletionService",
        description="Completion Service.",
    )
    component_2 = db.Component(
        id=MOCK_UUIDS["component_2"],
        name="Synthesizer",
        description="Synthesizer Component.",
    )
    component_3 = db.Component(
        id=MOCK_UUIDS["component_3"],
        name="Retriever",
        description="Retriever Component.",
    )
    component_4 = db.Component(
        id=MOCK_UUIDS["component_4"],
        name="ReActAgent",
        description="ReAct framework agent.",
        is_agent=True,
    )
    component_5 = db.Component(
        id=MOCK_UUIDS["component_5"],
        name="RAGAgent",
        description="Retrieve and Generate Agent.",
        is_agent=True,
    )
    component_6 = db.Component(
        id=MOCK_UUIDS["component_6"],
        name="EmbeddingService",
        description="Embedding Service.",
    )
    session.add_all([component_1, component_2, component_3, component_4, component_5, component_6])
    session.commit()

    # --- Tool Descriptions ---
    tool_description_1 = db.ToolDescription(
        id=MOCK_UUIDS["tool_description_1"],
        name="MockTool1",
        description="Mock tool description 1.",
        tool_properties={"prop1": "value1"},
        required_tool_properties={"req1": "value1"},
    )
    tool_description_2 = db.ToolDescription(
        id=MOCK_UUIDS["tool_description_2"],
        name="MockTool2",
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

    # --- Basic Parameters ---
    secret_param = db.BasicParameter(
        component_instance_id=component_instance_1.id,
        name="api_key",
        project_secret_id=project_secret_1.id,
        value_type=ParameterType.STRING,
    )
    param_1 = db.BasicParameter(
        component_instance_id=component_instance_1.id,
        name="temperature",
        value=0.8,
        value_type=ParameterType.FLOAT,
    )
    param_2 = db.BasicParameter(
        component_instance_id=component_instance_2.id,
        name="style",
        value="formal",
        value_type=ParameterType.STRING,
    )
    param_3 = db.BasicParameter(
        component_instance_id=component_instance_4.id,
        name="max_iterations",
        value=5,
        value_type=ParameterType.INTEGER,
    )
    param_4 = db.BasicParameter(
        component_instance_id=component_instance_5.id,
        name="retrieval_count",
        value=3,
        value_type=ParameterType.INTEGER,
    )
    session.add_all([param_1, param_2, param_3, param_4, secret_param])
    session.commit()

    # --- Component Sub-Inputs ---
    component_sub_input = db.ComponentSubInput(
        parent_component_instance_id=component_instance_2.id,
        child_component_instance_id=component_instance_1.id,
        parameter_name="llm_service",
    )
    session.add(component_sub_input)
    session.commit()

    # --- Component Relationships ---
    # ReActAgent uses Synthesizer
    agent_component_input = db.ComponentSubInput(
        parent_component_instance_id=component_instance_4.id,
        child_component_instance_id=component_instance_2.id,
        parameter_name="synthesizer",
    )
    # RAGAgent uses ReActAgent as a sub-agent
    agent_sub_agent_input = db.ComponentSubInput(
        parent_component_instance_id=component_instance_5.id,
        child_component_instance_id=component_instance_4.id,
        parameter_name="sub_agent",
    )
    session.add_all([agent_component_input, agent_sub_agent_input])
    session.commit()


def populate_ada_backend_db_from_seed(session: Session):
    """
    Populate the test database with mock data for ada_backend.
    """
    # --- Seed the database ---
    seed_db(session)


@pytest.fixture(scope="function")
def ada_backend_mock_session(test_db):
    """
    Provides a SQLAlchemy session for testing.
    Automatically rolls back changes after the test.
    """
    engine, SessionLocal = test_db  # Unpack the engine and session factory
    schema_name = getattr(engine, "test_schema", "public")
    connection = engine.connect()
    transaction = connection.begin()
    connection.execute(text(f"SET search_path TO {schema_name}"))
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
    schema_name = getattr(engine, "test_schema", "public")
    connection = engine.connect()
    transaction = connection.begin()
    connection.execute(text(f"SET search_path TO {schema_name}"))
    _session = SessionLocal(bind=connection)

    populate_ada_backend_db_from_seed(_session)

    yield _session

    _session.close()
    transaction.rollback()
    connection.close()
