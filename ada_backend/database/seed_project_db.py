from uuid import UUID, uuid4
import logging
import asyncio

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.demo.demo_graph_test import build_graph_test_chatbot, build_graph_test_source
from ada_backend.database.demo.demo_react_sql_tool import build_react_sql_agent_chatbot
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.database.utils import update_model_fields, models_are_equal

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


def upsert_projects(session: Session, projects: list[db.Project]) -> None:
    """
    Upserts a list of projects into the database.
    If a project with the same ID exists and has different attributes, it will be updated.
    If it exists and has the same attributes, it will be skipped.
    If a project with the same ID does not exist, it will be inserted.
    """
    for project in projects:
        existing_project = (
            session.query(db.Project)
            .filter(
                db.Project.id == project.id,
            )
            .first()
        )

        if existing_project:
            if models_are_equal(existing_project, project):
                LOGGER.info(f"Project {project.name} did not change, skipping.")
            else:
                update_model_fields(existing_project, project)
                LOGGER.info(f"Project {project.name} updated.")
        else:
            session.add(project)
            LOGGER.info(f"Project {project.name} inserted.")
    session.commit()


def upsert_graph_runners(session: Session, graph_runners: list[db.GraphRunner]) -> None:
    """
    Upserts a list of graph runners into the database.
    If a graph runner with the same ID exists and has different attributes, it will be updated.
    If it exists and has the same attributes, it will be skipped.
    If a graph runner with the same ID does not exist, it will be inserted.
    """
    for graph_runner in graph_runners:
        existing_graph_runner = (
            session.query(db.GraphRunner)
            .filter(
                db.GraphRunner.id == graph_runner.id,
            )
            .first()
        )

        if existing_graph_runner:
            if models_are_equal(existing_graph_runner, graph_runner):
                LOGGER.info(f"Graph runner {graph_runner.id} did not change, skipping.")
            else:
                update_model_fields(existing_graph_runner, graph_runner)
                LOGGER.info(f"Graph runner {graph_runner.id} updated.")
        else:
            session.add(graph_runner)
            LOGGER.info(f"Graph runner {graph_runner.id} inserted.")
    session.commit()


def upsert_project_environment_bindings(session: Session, bindings: list[db.ProjectEnvironmentBinding]) -> None:
    """
    Upserts a list of project environment bindings into the database.
    Looks up bindings by (project_id, environment) since there's a unique constraint on these fields.
    If a binding with the same project_id and environment exists and has different attributes, it will be updated.
    If it exists and has the same attributes, it will be skipped.
    If a binding with the same project_id and environment does not exist, it will be inserted.
    """
    for binding in bindings:
        existing_binding = (
            session.query(db.ProjectEnvironmentBinding)
            .filter(
                db.ProjectEnvironmentBinding.project_id == binding.project_id,
                db.ProjectEnvironmentBinding.environment == binding.environment,
            )
            .first()
        )

        if existing_binding:
            # Copy the ID from existing binding to the new one for comparison
            binding.id = existing_binding.id
            if models_are_equal(existing_binding, binding):
                LOGGER.info(
                    f"Project environment binding (project={binding.project_id}, "
                    f"env={binding.environment}) did not change, skipping."
                )
            else:
                update_model_fields(existing_binding, binding)
                LOGGER.info(
                    f"Project environment binding (project={binding.project_id}, "
                    f"env={binding.environment}) updated."
                )
        else:
            session.add(binding)
            LOGGER.info(
                f"Project environment binding (project={binding.project_id}, " f"env={binding.environment}) inserted."
            )
    session.commit()


def upsert_data_sources(session: Session, data_sources: list[db.DataSource]) -> None:
    """
    Upserts a list of data sources into the database.
    If a data source with the same ID exists and has different attributes, it will be updated.
    If it exists and has the same attributes, it will be skipped.
    If a data source with the same ID does not exist, it will be inserted.
    """
    for data_source in data_sources:
        existing_data_source = (
            session.query(db.DataSource)
            .filter(
                db.DataSource.id == data_source.id,
            )
            .first()
        )

        if existing_data_source:
            if models_are_equal(existing_data_source, data_source):
                LOGGER.info(f"Data source {data_source.name} did not change, skipping.")
            else:
                update_model_fields(existing_data_source, data_source)
                LOGGER.info(f"Data source {data_source.name} updated.")
        else:
            session.add(data_source)
            LOGGER.info(f"Data source {data_source.name} inserted.")
    session.commit()


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
        type=db.ProjectType.WORKFLOW,
    )
    graph_test_project = db.Project(
        id=PROJECT_UUIDS["graph_test_project"],
        name="Graph Test Project",
        description="Graph Test Project",
        organization_id=DEFAULT_ORGANIZATION_ID,
        type=db.ProjectType.WORKFLOW,
    )
    react_sql_agent_project = db.Project(
        id=PROJECT_UUIDS["react_sql_agent_chatbot"],
        name="React SQL Agent",
        description="React SQL Agent based on data gouv data (population : marriage, naissance, death)",
        organization_id=UUID("01b6554c-4884-409f-a0e1-22e394bee989"),
        type=db.ProjectType.WORKFLOW,
    )

    upsert_projects(
        session,
        [
            project_1,
            graph_test_project,
            react_sql_agent_project,
        ],
    )


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

    upsert_graph_runners(
        session,
        [
            graph_runner_prod,
            graph_runner_draft,
            react_sql_graph_runner_prod,
            react_sql_graph_runner_draft,
        ],
    )

    upsert_project_environment_bindings(
        session,
        [
            test_gr_relationship_prod,
            test_gr_relationship_draft,
            react_gr_relationship_prod,
            react_gr_relationship_draft,
        ],
    )


def seed_sources(session: Session):
    """
    Seed the database with a source component.
    """

    graph_test_source = build_graph_test_source(
        source_id=SOURCE_UUIDS["graph_test_source"],
        organization_id=DEFAULT_ORGANIZATION_ID,
    )
    upsert_data_sources(session, [graph_test_source])


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
            COMPONENT_VERSION_UUIDS,
            graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_prod"],
            source_id=SOURCE_UUIDS["graph_test_source"],
        )
        asyncio.run(
            update_graph_service(
                session,
                graph_project=graph_test_pipeline,
                graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_prod"],
                project_id=PROJECT_UUIDS["graph_test_project"],
                bypass_validation=True,
            )
        )
        LOGGER.info("Starting to build draft graph test project")
        graph_test_pipeline = build_graph_test_chatbot(
            COMPONENT_VERSION_UUIDS,
            graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_draft"],
            source_id=SOURCE_UUIDS["graph_test_source"],
        )
        asyncio.run(
            update_graph_service(
                session,
                graph_project=graph_test_pipeline,
                graph_runner_id=GRAPH_RUNNER_UUIDS["graph_runner_draft"],
                project_id=PROJECT_UUIDS["graph_test_project"],
                bypass_validation=True,
            )
        )

        LOGGER.info("Starting to build ReAct SQL Agent project")
        react_sql_agent_pipeline = build_react_sql_agent_chatbot(
            COMPONENT_VERSION_UUIDS, graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_prod"]
        )
        asyncio.run(
            update_graph_service(
                session,
                graph_project=react_sql_agent_pipeline,
                project_id=PROJECT_UUIDS["react_sql_agent_chatbot"],
                graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_prod"],
                bypass_validation=True,
            )
        )
        LOGGER.info("Starting to build ReAct SQL Agent draft project")
        react_sql_agent_staging = build_react_sql_agent_chatbot(
            COMPONENT_VERSION_UUIDS, graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_draft"]
        )
        asyncio.run(
            update_graph_service(
                session,
                graph_project=react_sql_agent_staging,
                project_id=PROJECT_UUIDS["react_sql_agent_chatbot"],
                graph_runner_id=GRAPH_RUNNER_UUIDS["react_sql_agent_draft"],
                bypass_validation=True,
            )
        )

    finally:
        session.close()


if __name__ == "__main__":
    import logging
    from ada_backend.database.setup_db import get_db

    logging.basicConfig(level=logging.INFO)

    print("Seeding projects in database...")
    seed_projects_db(next(get_db()))
