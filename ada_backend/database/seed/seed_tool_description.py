from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import upsert_tool_descriptions
from ada_backend.database.utils import DEFAULT_TOOL_DESCRIPTION
from engine.components.ai_agent import get_dummy_ai_agent_description
from engine.components.document_enhanced_llm_call import DEFAULT_DOCUMENT_ENHANCED_LLM_CALL_TOOL_DESCRIPTION
from engine.components.docx_generation_tool import DEFAULT_DOCX_GENERATION_TOOL_DESCRIPTION
from engine.components.filter import DEFAULT_FILTER_TOOL_DESCRIPTION
from engine.components.inputs_outputs.start import DEFAULT_START_TOOL_DESCRIPTION
from engine.components.llm_call import DEFAULT_LLM_CALL_TOOL_DESCRIPTION
from engine.components.pdf_generation_tool import DEFAULT_PDF_GENERATION_TOOL_DESCRIPTION
from engine.components.rag.rag import format_rag_tool_description
from engine.components.sql.react_sql_tool import DEFAULT_REACT_SQL_TOOL_DESCRIPTION
from engine.components.sql.run_sql_query_tool import DEFAULT_RUN_SQL_QUERY_TOOL_DESCRIPTION
from engine.components.table_lookup import DEFAULT_TABLE_LOOKUP_TOOL_DESCRIPTION
from engine.components.tools.api_call_tool import API_CALL_TOOL_DESCRIPTION
from engine.components.tools.docx_template import DOCX_TEMPLATE_TOOL_DESCRIPTION
from engine.components.tools.linkup_tool import LINKUP_TOOL_DESCRIPTION
from engine.components.tools.python_code_runner import PYTHON_CODE_RUNNER_TOOL_DESCRIPTION
from engine.components.tools.remote_mcp_tool import DEFAULT_REMOTE_MCP_TOOL_DESCRIPTION
from engine.components.tools.tavily_search_tool import TAVILY_TOOL_DESCRIPTION
from engine.components.tools.terminal_command_runner import TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION
from engine.components.web_search_tool_openai import DEFAULT_WEB_SEARCH_OPENAI_TOOL_DESCRIPTION
from engine.integrations.gmail_sender import GMAIL_SENDER_TOOL_DESCRIPTION

TOOL_DESCRIPTION_UUIDS = {
    "default_ai_agent_description": UUID("1a4d4098-c2b4-4078-96a6-0a8f9c7d018c"),
    "tavily_tool_description": UUID("768450eb-b07a-4efc-bbb9-48c9b1a9f556"),
    "default_api_call_tool_description": UUID("030b0418-1d7e-4764-8406-1875aec47c2d"),
    "default_react_sql_tool_description": UUID("3e2cc209-dc89-45a1-9c90-58a2c35fd574"),
    "default_rag_tool_description": UUID("e0f7719c-cc5c-4c71-9db0-b161875d1144"),
    "default_run_sql_query_tool_description": UUID("949c27b4-5403-42b0-bad6-1c71a7a4e5d1"),
    "default_tool_description": UUID("15e1198f-850a-4f66-91d7-34286de52795"),
    "default_web_search_openai_tool_description": UUID("b6d6d281-6c75-4d1b-a750-40b53deea3f5"),
    "default_document_enhanced_llm_agent": UUID("d01978d9-c785-4492-9e71-7af0aa8c05f7"),
    "default_input_tool_description": UUID("5be22376-7d08-486b-a004-b495bae58f77"),
    "default_filter_tool_description": UUID("6cf33487-8e19-597c-b115-c5a6cbf69a88"),
    "gmail_sender_tool_description": UUID("c1d3aca1-5187-40c6-a350-e3b28b15c802"),
    "python_code_runner_tool_description": UUID("e2b11111-2222-3333-4444-555555555555"),
    "terminal_command_runner_tool_description": UUID("e2b11112-2222-3333-4444-555555555555"),
    "default_llm_call_tool_description": UUID("b91d418d-a67f-40b9-9266-b01ca202747d"),
    "default_pdf_generation_tool_description": UUID("e2b11113-2222-3333-4444-555555555555"),
    "linkup_search_tool_description": UUID("d2e3f456-789a-bcde-f012-3456789abcde"),
    "default_docx_generation_tool_description": UUID("d57c546b-9f9d-4207-bb6e-0e38b2a3bce5"),
    "docx_template_tool_description": UUID("e2b22222-3333-4444-5555-666666666666"),
    "remote_mcp_tool_description": UUID("4c6ef0d2-53c0-4ab2-96cb-3c2b5f5b3e88"),
    "default_table_lookup_tool_description": UUID("5c6d7e8f-9012-3456-789a-bcdef0123456"),
}


def seed_tool_description(session: Session):
    default_ai_agent_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_ai_agent_description"], **get_dummy_ai_agent_description().model_dump()
    )
    default_tavily_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["tavily_tool_description"], **TAVILY_TOOL_DESCRIPTION.model_dump()
    )
    default_api_call_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_api_call_tool_description"], **API_CALL_TOOL_DESCRIPTION.model_dump()
    )
    default_react_sql_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_react_sql_tool_description"],
        **DEFAULT_REACT_SQL_TOOL_DESCRIPTION.model_dump(),
    )
    default_rag_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_rag_tool_description"],
        **format_rag_tool_description(source="notion").model_dump(),
    )
    default_run_sql_query_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_run_sql_query_tool_description"],
        **DEFAULT_RUN_SQL_QUERY_TOOL_DESCRIPTION.model_dump(),
    )
    default_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_tool_description"], **DEFAULT_TOOL_DESCRIPTION.model_dump()
    )
    default_web_search_openai_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_web_search_openai_tool_description"],
        **DEFAULT_WEB_SEARCH_OPENAI_TOOL_DESCRIPTION.model_dump(),
    )
    default_document_enhanced_llm_agent = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_document_enhanced_llm_agent"],
        **DEFAULT_DOCUMENT_ENHANCED_LLM_CALL_TOOL_DESCRIPTION.model_dump(),
    )
    default_start_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_input_tool_description"], **DEFAULT_START_TOOL_DESCRIPTION.model_dump()
    )
    default_filter_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_filter_tool_description"], **DEFAULT_FILTER_TOOL_DESCRIPTION.model_dump()
    )
    python_code_runner_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["python_code_runner_tool_description"],
        **PYTHON_CODE_RUNNER_TOOL_DESCRIPTION.model_dump(),
    )
    terminal_command_runner_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["terminal_command_runner_tool_description"],
        **TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION.model_dump(),
    )
    gmail_sender_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["gmail_sender_tool_description"],
        **GMAIL_SENDER_TOOL_DESCRIPTION.model_dump(),
    )
    default_llm_call_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_llm_call_tool_description"],
        **DEFAULT_LLM_CALL_TOOL_DESCRIPTION.model_dump(),
    )
    pdf_generation_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_pdf_generation_tool_description"],
        **DEFAULT_PDF_GENERATION_TOOL_DESCRIPTION.model_dump(),
    )
    linkup_search_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["linkup_search_tool_description"],
        **LINKUP_TOOL_DESCRIPTION.model_dump(),
    )
    docx_generation_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_docx_generation_tool_description"],
        **DEFAULT_DOCX_GENERATION_TOOL_DESCRIPTION.model_dump(),
    )
    docx_template_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["docx_template_tool_description"],
        **DOCX_TEMPLATE_TOOL_DESCRIPTION.model_dump(),
    )
    remote_mcp_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["remote_mcp_tool_description"],
        **DEFAULT_REMOTE_MCP_TOOL_DESCRIPTION.model_dump(),
    )
    default_table_lookup_tool_description = db.ToolDescription(
        id=TOOL_DESCRIPTION_UUIDS["default_table_lookup_tool_description"],
        **DEFAULT_TABLE_LOOKUP_TOOL_DESCRIPTION.model_dump(),
    )
    upsert_tool_descriptions(
        session=session,
        tool_descriptions=[
            default_ai_agent_description,
            default_tavily_tool_description,
            default_api_call_tool_description,
            default_react_sql_tool_description,
            default_rag_tool_description,
            default_run_sql_query_tool_description,
            default_tool_description,
            default_web_search_openai_tool_description,
            default_document_enhanced_llm_agent,
            default_start_tool_description,
            default_filter_tool_description,
            gmail_sender_tool_description,
            python_code_runner_tool_description,
            terminal_command_runner_tool_description,
            default_llm_call_tool_description,
            pdf_generation_tool_description,
            linkup_search_tool_description,
            docx_generation_tool_description,
            docx_template_tool_description,
            remote_mcp_tool_description,
            default_table_lookup_tool_description,
        ],
    )
