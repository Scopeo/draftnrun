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
from ada_backend.database.seed.integrations.seed_gmail import seed_gmail_components, seed_gmail_parameter_groups
from ada_backend.database.seed.integrations.seed_integration import seed_integrations
from ada_backend.database.seed.integrations.seed_mcp_google_calendar import seed_mcp_google_calendar_components
from ada_backend.database.seed.integrations.seed_mcp_hubspot import seed_mcp_hubspot_components
from ada_backend.database.seed.integrations.seed_mcp_hubspot_neverdrop import seed_mcp_hubspot_neverdrop_components
from ada_backend.database.seed.integrations.seed_mail_sender import (
    seed_mail_sender_component_parameter_groups,
    seed_mail_sender_components,
    seed_mail_sender_parameter_groups,
)
from ada_backend.database.seed.integrations.seed_outlook import seed_outlook_components, seed_outlook_parameter_groups
from ada_backend.database.seed.integrations.seed_slack import seed_slack_components
from ada_backend.database.seed.seed_ai_agent import seed_ai_agent_components, seed_ai_agent_parameter_groups
from ada_backend.database.seed.seed_api_call_tool import seed_api_call_components
from ada_backend.database.seed.seed_categories import seed_categories
from ada_backend.database.seed.seed_categorizer import seed_categorizer_components, seed_categorizer_parameter_groups
from ada_backend.database.seed.seed_chunk_processor import seed_chunk_processor_components
from ada_backend.database.seed.seed_db_service import seed_db_service_components
from ada_backend.database.seed.seed_docx_generation import seed_docx_generation_components
from ada_backend.database.seed.seed_docx_template import seed_docx_template_components
from ada_backend.database.seed.seed_filter import seed_filter_components
from ada_backend.database.seed.seed_if_else import seed_if_else_components
from ada_backend.database.seed.seed_linkup_tool import seed_linkup_tool_components, seed_linkup_tool_parameter_groups
from ada_backend.database.seed.seed_llm_call import seed_llm_call_components, seed_llm_call_parameter_groups
from ada_backend.database.seed.seed_ocr_call import seed_ocr_call_components
from ada_backend.database.seed.seed_pdf_generation import seed_pdf_generation_components
from ada_backend.database.seed.seed_ports import seed_port_definitions
from ada_backend.database.seed.seed_project_reference import seed_project_reference_components
from ada_backend.database.seed.seed_python_code_runner import seed_python_code_runner_components
from ada_backend.database.seed.seed_rag import seed_rag_components, seed_rag_v3_parameter_groups
from ada_backend.database.seed.seed_rag_v4 import seed_rag_v4_components, seed_rag_v4_parameter_groups
from ada_backend.database.seed.seed_react_sql import seed_react_sql_components
from ada_backend.database.seed.seed_remote_mcp_tool import seed_remote_mcp_tool_components
from ada_backend.database.seed.seed_retriever_tool import seed_retriever_tool_components
from ada_backend.database.seed.seed_router import seed_router_components
from ada_backend.database.seed.seed_scorer import seed_scorer_components, seed_scorer_parameter_groups
from ada_backend.database.seed.seed_sql_tool import seed_sql_tool_components
from ada_backend.database.seed.seed_start import seed_start_components
from ada_backend.database.seed.seed_static_responder import seed_static_responder_components
from ada_backend.database.seed.seed_table_lookup import seed_table_lookup_components
from ada_backend.database.seed.seed_terminal_command_runner import seed_terminal_command_runner_components
from ada_backend.database.seed.seed_tool_description import seed_tool_description
from ada_backend.database.seed.seed_web_search import seed_web_search_components
from ada_backend.database.seed.utils import COMPONENT_UUIDS, seed_anthropic_models, seed_custom_llm_models

LOGGER = logging.getLogger(__name__)


def seed_db(session: Session):
    """
    Seed the database with initial data.
    """
    try:
        seed_integrations(session)
        seed_categories(session)
        seed_tool_description(session)
        session.commit()

        seed_db_service_components(session)
        session.commit()

        seed_ai_agent_components(session)
        seed_ai_agent_parameter_groups(session)
        session.commit()

        seed_rag_components(session)
        seed_rag_v3_parameter_groups(session)
        seed_rag_v4_components(session)
        seed_rag_v4_parameter_groups(session)
        session.commit()

        seed_api_call_components(session)
        session.commit()

        seed_python_code_runner_components(session)
        session.commit()

        seed_terminal_command_runner_components(session)
        session.commit()

        seed_pdf_generation_components(session)
        session.commit()

        seed_docx_generation_components(session)
        session.commit()

        seed_docx_template_components(session)
        session.commit()

        seed_llm_call_components(session)
        seed_llm_call_parameter_groups(session)
        session.commit()

        seed_categorizer_components(session)
        seed_categorizer_parameter_groups(session)
        session.commit()

        seed_sql_tool_components(session)
        session.commit()

        seed_react_sql_components(session)
        session.commit()

        seed_web_search_components(session)
        session.commit()

        seed_ocr_call_components(session)
        session.commit()

        seed_start_components(session)
        session.commit()

        seed_filter_components(session)
        session.commit()

        seed_if_else_components(session)
        session.commit()

        seed_router_components(session)
        session.commit()

        seed_gmail_components(session)
        seed_gmail_parameter_groups(session)
        session.commit()

        seed_slack_components(session)
        session.commit()

        seed_mcp_hubspot_components(session)
        session.commit()

        seed_mcp_hubspot_neverdrop_components(session)
        seed_mcp_google_calendar_components(session)
        session.commit()

        seed_outlook_components(session)
        seed_outlook_parameter_groups(session)
        session.commit()

        seed_mail_sender_parameter_groups(session)
        seed_mail_sender_components(session)
        seed_mail_sender_component_parameter_groups(session)
        session.commit()

        seed_project_reference_components(session)
        session.commit()

        seed_chunk_processor_components(session)
        session.commit()

        seed_linkup_tool_components(session)
        seed_linkup_tool_parameter_groups(session)
        session.commit()

        seed_retriever_tool_components(session)
        session.commit()

        seed_static_responder_components(session)
        session.commit()

        seed_table_lookup_components(session)
        session.commit()

        seed_remote_mcp_tool_components(session)
        session.commit()

        seed_scorer_components(session)
        seed_scorer_parameter_groups(session)
        session.commit()

        seed_port_definitions(session)
        seed_custom_llm_models(session)
        seed_anthropic_models(session)
        session.commit()

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
