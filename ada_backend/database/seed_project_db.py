from uuid import UUID, uuid4
import logging
import asyncio

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.demo.demo_graph_test import build_graph_test_chatbot, build_graph_test_source
from ada_backend.database.demo.demo_react_sql_tool import build_react_sql_agent_chatbot
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.database.seed_db import COMPONENT_UUIDS
from engine.trace.trace_context import get_trace_manager, set_trace_manager
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


PROJECT_UUIDS: dict[str, UUID] = {
    "project_1": uuid4(),
    "graph_test_project": UUID("f7ddbfcb-6843-4ae9-a15b-40aa565b955b"),
    "react_sql_agent_chatbot": UUID("c76400a2-ab48-4cbc-bcb1-a703c1b62f47"),
}

GRAPH_RUNNER_UUIDS: dict[str, UUID] = {
    "graph_runner_prod": UUID("f7ddbfcb-6843-4ae9-a15b-40aa565b955b"),
    "graph_runner_draft": UUID("767bb69b-171e-4844-a373-06f8ee3a6843"),
    "react_sql_agent_prod": UUID("8c3d124d-0049-49ac-ab5b-2fc0e695ec22"),
    "react_sql_agent_draft": UUID("becd7d4f-d691-479a-8746-d123dc035599"),
}

SOURCE_UUIDS: dict[str, UUID] = {
    "graph_test_source": UUID("ff39489a-ac21-4a5a-8ea6-e21f510b3538"),
}
DEFAULT_ORGANIZATION_ID = UUID("37b7d67f-8f29-4fce-8085-19dea582f605")


def seed_projects(session: Session):
    """
    Seed the database with some projects and project-component relationships.
    """

    # --- Define projects ---
    project_1 = db.Project(
        id=PROJECT_UUIDS["project_1"],
        name="Project1",
        description="Project 1",
        organization_id=DEFAULT_ORGANIZATION_ID,
    )
    graph_test_project = db.Project(
        id=PROJECT_UUIDS["graph_test_project"],
        name="Graph Test Project",
        description="Graph Test Project",
        organization_id=DEFAULT_ORGANIZATION_ID,
        companion_image_url=(
            "https://pjnpfnqwglwxvpaookdh.supabase.co/storage/v1/object/public/ada-public/"
            "companion_images/arthur_createur_de_companions_sur_mesure.png"
        ),
    )
    react_sql_agent_project = db.Project(
        id=PROJECT_UUIDS["react_sql_agent_chatbot"],
        name="React SQL Agent",
        description="React SQL Agent based on data gouv data (population : marriage, naissance, death)",
        organization_id=UUID("01b6554c-4884-409f-a0e1-22e394bee989"),
        companion_image_url=(
            "https://pjnpfnqwglwxvpaookdh.supabase.co/storage/v1/object/public/"
            "ada-public/companion_images/mia_administration_des_ventes.png"
        ),
    )

    session.add_all(
        [
            project_1,
            graph_test_project,
            react_sql_agent_project,
        ]
    )
    session.commit()


def seed_graph_runner(session: Session):
    """
    Seed the database with a graph runner component.
    """

    # Graph Runners
    graph_runner_prod = db.GraphRunner(
        id=GRAPH_RUNNER_UUIDS["graph_runner_prod"],
    )
    test_gr_relationship_prod = db.ProjectEnvironmentBinding(
        project_id=PROJECT_UUIDS["graph_test_project"],
        graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_prod"],
        environment=db.EnvType.PRODUCTION,
    )
    graph_runner_draft = db.GraphRunner(
        id=GRAPH_RUNNER_UUIDS["graph_runner_draft"],
    )
    test_gr_relationship_draft = db.ProjectEnvironmentBinding(
        project_id=PROJECT_UUIDS["graph_test_project"],
        graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_draft"],
        environment=db.EnvType.DRAFT,
    )
    react_sql_graph_runner_prod = db.GraphRunner(
        id=GRAPH_RUNNER_UUIDS["react_sql_agent_prod"],
    )
    react_gr_relationship_prod = db.ProjectEnvironmentBinding(
        project_id=PROJECT_UUIDS["react_sql_agent_chatbot"],
        graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_prod"],
        environment=db.EnvType.PRODUCTION,
    )
    react_sql_graph_runner_draft = db.GraphRunner(
        id=GRAPH_RUNNER_UUIDS["react_sql_agent_draft"],
    )
    react_gr_relationship_draft = db.ProjectEnvironmentBinding(
        project_id=PROJECT_UUIDS["react_sql_agent_chatbot"],
        graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_draft"],
        environment=db.EnvType.DRAFT,
    )

    session.add_all(
        [
            graph_runner_prod,
            graph_runner_draft,
            react_sql_graph_runner_prod,
            react_sql_graph_runner_draft,
        ]
    )
    session.commit()

    session.add_all(
        [
            test_gr_relationship_prod,
            test_gr_relationship_draft,
            react_gr_relationship_prod,
            react_gr_relationship_draft,
        ]
    )
    session.commit()


def seed_sources(session: Session):
    """
    Seed the database with a source component.
    """

    graph_test_source = build_graph_test_source(
        source_id=SOURCE_UUIDS["graph_test_source"],
        organization_id=DEFAULT_ORGANIZATION_ID,
    )
    session.add(graph_test_source)
    session.commit()


def seed_projects_db(session: Session):
    """
    Seed the database with initial data.
    """
    try:
        # Then seed projects and other data that depends on components
        seed_sources(session)
        seed_projects(session)
        seed_graph_runner(session)

        project = session.query(db.Project).filter_by(name="Project1").first()
        if not project:
            raise ValueError("Project1 not found. Ensure the project exists before seeding the pipeline.")

        LOGGER.info("Starting to build prod graph test project")
        graph_test_pipeline = build_graph_test_chatbot(
            COMPONENT_UUIDS,
            graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_prod"],
            source_id=SOURCE_UUIDS["graph_test_source"],
        )
        asyncio.run(
            update_graph_service(
                session,
                graph_project=graph_test_pipeline,
                graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_prod"],
                project_id=PROJECT_UUIDS["graph_test_project"],
            )
        )
        LOGGER.info("Starting to build draft graph test project")
        graph_test_pipeline = build_graph_test_chatbot(
            COMPONENT_UUIDS,
            graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_draft"],
            source_id=SOURCE_UUIDS["graph_test_source"],
        )
        asyncio.run(
            update_graph_service(
                session,
                graph_project=graph_test_pipeline,
                graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_draft"],
                project_id=PROJECT_UUIDS["graph_test_project"],
            )
        )

        LOGGER.info("Starting to build ReAct SQL Agent project")
        react_sql_agent_pipeline = build_react_sql_agent_chatbot(
            COMPONENT_UUIDS, graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_prod"]
        )
        asyncio.run(
            update_graph_service(
                session,
                graph_project=react_sql_agent_pipeline,
                project_id=PROJECT_UUIDS["react_sql_agent_chatbot"],
                graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_prod"],
            )
        )
        LOGGER.info("Starting to build ReAct SQL Agent draft project")
        react_sql_agent_staging = build_react_sql_agent_chatbot(
            COMPONENT_UUIDS, graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_draft"]
        )
        asyncio.run(
            update_graph_service(
                session,
                graph_project=react_sql_agent_staging,
                project_id=PROJECT_UUIDS["react_sql_agent_chatbot"],
                graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_draft"],
            )
        )

    finally:
        session.close()


if __name__ == "__main__":
    import logging
    from ada_backend.database.setup_db import get_db

    logging.basicConfig(level=logging.INFO)

    set_trace_manager(TraceManager(project_name="ada_backend"))
    trace_manager = get_trace_manager()
    trace_manager.organization_id = DEFAULT_ORGANIZATION_ID
    trace_manager.project_id = PROJECT_UUIDS["project_1"]
    trace_manager.organization_llm_providers = ["openai", "anthropic", "cohere"]

    print("Seeding projects in database...")
    seed_projects_db(next(get_db()))
