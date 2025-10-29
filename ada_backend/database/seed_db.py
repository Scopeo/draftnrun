"""
This script seeds the database with initial data.
Useful for development and testing purposes.
Should be replaced soon by a agent-configurator service/API.
TODO: Implement agent-configurator service/API and remove this script or
move it to tests/mocks.
"""

import logging

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.seed.integrations.seed_integration import seed_integrations
from ada_backend.database.seed.seed_ai_agent import seed_ai_agent_components, seed_ai_agent_parameter_groups
from ada_backend.database.seed.seed_categories import seed_categories
from ada_backend.database.seed.seed_db_service import seed_db_service_components
from ada_backend.database.seed.integrations.seed_gmail import seed_gmail_components
from ada_backend.database.seed.seed_linkup_tool import seed_linkup_tool_components
from ada_backend.database.seed.seed_start import seed_start_components
from ada_backend.database.seed.seed_filter import seed_filter_components
from ada_backend.database.seed.seed_llm_call import seed_llm_call_components
from ada_backend.database.seed.seed_rag import seed_rag_components
from ada_backend.database.seed.seed_react_sql import seed_react_sql_components
from ada_backend.database.seed.seed_smart_rag import seed_smart_rag_components
from ada_backend.database.seed.seed_sql_tool import seed_sql_tool_components
from ada_backend.database.seed.seed_tavily import seed_tavily_components
from ada_backend.database.seed.seed_api_call_tool import seed_api_call_components
from ada_backend.database.seed.seed_python_code_runner import seed_python_code_runner_components
from ada_backend.database.seed.seed_terminal_command_runner import seed_terminal_command_runner_components
from ada_backend.database.seed.seed_web_search import seed_web_search_components
from ada_backend.database.seed.seed_ocr_call import seed_ocr_call_components
from ada_backend.database.seed.seed_pdf_generation import seed_pdf_generation_components
from ada_backend.database.seed.seed_docx_generation import seed_docx_generation_components
from ada_backend.database.seed.seed_project_reference import seed_project_reference_components
from ada_backend.database.seed.seed_chunk_processor import seed_chunk_processor_components
from ada_backend.database.seed.seed_static_responder import seed_static_responder_components
from ada_backend.database.seed.seed_tool_description import seed_tool_description
from ada_backend.database.seed.seed_ports import seed_port_definitions
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


LOGGER = logging.getLogger(__name__)


def seed_db(session: Session):
    """
    Seed the database with initial data.
    """
    try:
        seed_integrations(session)
        seed_categories(session)
        # First seed the available components
        seed_tool_description(session)
        seed_db_service_components(session)
        seed_ai_agent_components(session)
        seed_ai_agent_parameter_groups(session)
        seed_rag_components(session)
        seed_api_call_components(session)
        seed_python_code_runner_components(session)
        seed_terminal_command_runner_components(session)
        seed_pdf_generation_components(session)
        seed_docx_generation_components(session)
        seed_tavily_components(session)
        seed_llm_call_components(session)
        seed_sql_tool_components(session)
        seed_react_sql_components(session)
        seed_smart_rag_components(session)
        seed_web_search_components(session)
        seed_ocr_call_components(session)
        seed_start_components(session)
        seed_filter_components(session)
        seed_gmail_components(session)
        seed_project_reference_components(session)
        seed_chunk_processor_components(session)
        seed_linkup_tool_components(session)
        seed_static_responder_components(session)

        # Seed port definitions from code (with upsert)
        seed_port_definitions(session)

        # Verify components exist
        for name, uuid_value in COMPONENT_UUIDS.items():
            component = session.query(db.Component).filter_by(id=uuid_value).first()
            if not component:
                raise ValueError(f"Component {name} with ID {uuid_value} was not properly seeded")
    finally:
        session.close()


if __name__ == "__main__":
    import logging
    from ada_backend.database.setup_db import get_db

    logging.basicConfig(level=logging.INFO)

    print("Seeding database...")
    seed_db(next(get_db()))
