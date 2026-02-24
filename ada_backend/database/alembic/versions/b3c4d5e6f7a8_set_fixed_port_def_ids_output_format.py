"""Set fixed port definition IDs for all input and output ports.

Replaces existing port_definition IDs with fixed UUIDs for every port we have
a fixed ID for (engine port_definition_ids). So prod and seed stay aligned:
same port always has the same id, no data loss.

For each (component_version, name, port_type): copy the row to the new fixed id,
update all FKs (input_port_instances, port_mappings), then delete the old row.
Rows that don't exist yet (e.g. component not seeded) are skipped.

UUIDs and component version IDs must match engine port_definition_ids and
seed utils.COMPONENT_VERSION_UUIDS.

Revision ID: b3c4d5e6f7a8
Revises: 6c3f812c5752
Create Date: 2026-02-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "6c3f812c5752"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Component version IDs (from seed utils.COMPONENT_VERSION_UUIDS).
CV = {
    "llm_call": "7a039611-49b3-4bfd-b09b-c0f93edf3b79",
    "base_ai_agent": "22292e7f-a3ba-4c63-a4c7-dd5c0c75cdaa",
    "static_responder": "1F7334BE-7164-4440-BBF3-E986EED0388F",
    "filter": "02468c0b-bc99-44ce-a435-995acc5e2545",
    "if_else": "ce974746-4246-4300-828f-cf8553773616",
    "table_lookup": "4b5c6d7e-8f90-1234-5678-9abcdef01234",
    "rag_agent_v3": "f1a5b6c7-d8e9-4f0a-1b2c-3d4e5f6a7b8c",  # RAG
    "retriever_tool": "2d8a4f3e-1c6b-4a9d-8f27-3e6b5a1c9d02",
    "terminal_command_runner": "e2b10000-1111-2222-3333-444444444444",
    "python_code_runner": "e2b00000-0000-1111-2222-333333333333",
    "pdf_generation": "428baac0-0c5f-4374-b2de-8075218082b4",
    "docx_generation": "b5195a0f-94f5-4f5c-8804-32dd19b16833",
    "linkup_search_tool": "f3e45678-9abc-def0-1234-56789abcdef0",
    "web_search_openai_agent_v2": "d6020df0-a7e0-4d82-b731-0a653beef2e5",
    "hubspot_mcp_tool": "71cc6f88-74a8-4270-8428-f538c152584c",
    "docx_template_agent": "e2b30000-3333-4444-5555-666666666666",
    "remote_mcp_tool": "5e472b85-7601-4e5b-81c7-8b361b5c5c9a",
}

# (component_version_key, port name, port_type, fixed UUID)
# Must match engine.components.port_definition_ids and seed port names.
PORT_MIGRATIONS = [
    # LLM Call
    ("llm_call", "messages", "INPUT", "c0d4a691-804b-55eb-bb8c-f60de6f58cea"),
    ("llm_call", "prompt_template", "INPUT", "a5ce402b-219f-5a4b-aeef-05e608c8094f"),
    ("llm_call", "output_format", "INPUT", "b2c3d4e5-f6a7-4789-8012-3456789abcde"),
    ("llm_call", "output", "OUTPUT", "243e6363-7e2b-581e-9c7f-392a2a22f053"),
    ("llm_call", "artifacts", "OUTPUT", "1448a2b3-abe8-5d0d-ac59-73d7a74468b3"),
    # AI Agent
    ("base_ai_agent", "messages", "INPUT", "9cd1d16c-88ce-56e9-ace4-fda9d208fdcb"),
    ("base_ai_agent", "initial_prompt", "INPUT", "90089d14-2bbc-5224-868f-5e8d00084431"),
    ("base_ai_agent", "output_format", "INPUT", "c3d4e5f6-a7b8-4901-9012-3456789abcdf"),
    ("base_ai_agent", "output", "OUTPUT", "fe81e36c-fb8d-5500-ba41-3f5b1be1be09"),
    ("base_ai_agent", "full_message", "OUTPUT", "2a224fdf-7e4d-5b4e-9a7b-660e16739bb5"),
    ("base_ai_agent", "is_final", "OUTPUT", "3c31134a-59f6-57e2-bd3b-a78dbc3ad343"),
    ("base_ai_agent", "artifacts", "OUTPUT", "645cbf1d-2716-54db-a5f1-0a01d663795f"),
    # Static Responder
    ("static_responder", "input", "INPUT", "dadb9596-3514-5ac3-bf43-39e2faaa10b5"),
    ("static_responder", "input_from_previous", "OUTPUT", "9f5a40be-1c4c-530c-b6b9-ec8d6b328aa4"),
    ("static_responder", "static_message", "OUTPUT", "892cc8e6-c0b9-5448-a8e5-c3bb1c31223e"),
    # Filter
    ("filter", "messages", "INPUT", "01ebc4de-90bf-52d8-a2ef-3327b42c1375"),
    ("filter", "error", "INPUT", "405fcd4f-7940-5e73-81df-c3028fbe98fa"),
    ("filter", "artifacts", "INPUT", "ea6ef52d-074a-55ae-ace4-68dd928a2126"),
    ("filter", "is_final", "INPUT", "b4a87161-25ab-5552-9320-f9ee25744134"),
    ("filter", "output", "OUTPUT", "caad74c0-db46-5547-bd17-4002381f1699"),
    ("filter", "is_final", "OUTPUT", "261b08d8-9aba-5db3-94e7-4b5370c5dd29"),
    ("filter", "artifacts", "OUTPUT", "cfa90f8e-0aa9-5840-932c-98d911d1c388"),
    # If/Else
    ("if_else", "conditions", "INPUT", "561890ca-d8f8-59eb-8f5c-740d255f5bf3"),
    ("if_else", "output_value_if_true", "INPUT", "d0fc1698-9135-53b5-923e-4aad1af48e65"),
    ("if_else", "result", "OUTPUT", "fd7070e4-3b00-59db-be96-4a78f8e5108a"),
    ("if_else", "output", "OUTPUT", "14d060e8-e868-53b9-8770-7c5db070bbe5"),
    ("if_else", "should_halt", "OUTPUT", "e27c22d3-c147-5023-ad88-93c8e0b78917"),
    # Table Lookup
    ("table_lookup", "lookup_key", "INPUT", "f54f38dd-5296-568b-bdd1-f60240842798"),
    ("table_lookup", "lookup_value", "OUTPUT", "04bd46e1-46b6-51bb-b4cd-453bb137040f"),
    # RAG (rag_agent_v3)
    ("rag_agent_v3", "query_text", "INPUT", "15925ea7-1ce5-5054-bce2-6811cb7376d6"),
    ("rag_agent_v3", "filters", "INPUT", "13d8c92c-ab62-5213-b902-3faa3b47b00c"),
    ("rag_agent_v3", "output", "OUTPUT", "eb1f374b-d9fc-57b5-91da-6960662b79a5"),
    ("rag_agent_v3", "is_final", "OUTPUT", "7ad047d9-c8c1-54f9-adf6-a282c37d8ba5"),
    ("rag_agent_v3", "artifacts", "OUTPUT", "167ee096-2d0d-5d6b-9bca-7f10a2e598ba"),
    # Retriever
    ("retriever_tool", "query", "INPUT", "e7d48658-5d40-5477-8ab2-426be7de14f1"),
    ("retriever_tool", "filters", "INPUT", "9c9afb0a-25c1-5e39-a04d-b92dbcd76011"),
    ("retriever_tool", "formatted_content", "OUTPUT", "ac5ff0e7-d546-5377-a8ba-0e37e43f7335"),
    ("retriever_tool", "artifacts", "OUTPUT", "5414eb01-a237-58f1-8536-e1b0a04ade0d"),
    # Terminal Command Runner
    ("terminal_command_runner", "command", "INPUT", "94c477b0-42fe-5fed-9302-49081cfd8249"),
    ("terminal_command_runner", "output", "OUTPUT", "bd047f71-760f-5a74-afef-3deeb27126bc"),
    ("terminal_command_runner", "artifacts", "OUTPUT", "5fe72a50-0d97-5aed-8084-ff4ecf471b7e"),
    # Python Code Runner
    ("python_code_runner", "python_code", "INPUT", "91259a1e-9d35-50e0-b1c9-622039bb56c3"),
    ("python_code_runner", "input_filepaths", "INPUT", "d95ef69d-05a4-53d3-9e2e-80775c8e7ea5"),
    ("python_code_runner", "output", "OUTPUT", "42f0840d-8025-5168-bc2b-59172d26a6a7"),
    ("python_code_runner", "artifacts", "OUTPUT", "17c2328f-b775-5b08-be82-3e91f2f24ff6"),
    # PDF Generation
    ("pdf_generation", "markdown_content", "INPUT", "bf5232e1-4b1f-5e54-9edd-20bcd7f70ded"),
    ("pdf_generation", "filename", "INPUT", "9dfdc9ea-7a11-52ed-afce-95fc048c16e9"),
    ("pdf_generation", "output_message", "OUTPUT", "c6e29894-0016-52c5-84c9-07822f7d4b33"),
    ("pdf_generation", "artifacts", "OUTPUT", "966fd293-494b-5243-bf5e-f33762b81636"),
    # DOCX Generation
    ("docx_generation", "markdown_content", "INPUT", "1c8f7960-2ea7-5f06-a890-c47fa67e2ea5"),
    ("docx_generation", "filename", "INPUT", "1a5434b2-9e7a-5541-82ff-8e114d83ac99"),
    ("docx_generation", "output_message", "OUTPUT", "481c7d14-ee9b-54c9-8d6a-b0612d2de5ff"),
    ("docx_generation", "artifacts", "OUTPUT", "874ec409-6826-5f86-a24e-c671b0d39fa0"),
    # Linkup Search Tool
    ("linkup_search_tool", "query", "INPUT", "a22b9583-3236-5860-9efc-00b37b11232d"),
    ("linkup_search_tool", "depth", "INPUT", "c06fb129-e023-5c7a-a55f-82dec5b54c5b"),
    ("linkup_search_tool", "from_date", "INPUT", "d2408a80-1caf-5d20-a237-62b1e0bc1dab"),
    ("linkup_search_tool", "to_date", "INPUT", "252376ed-93a3-5256-ae21-559cf720a606"),
    ("linkup_search_tool", "include_domains", "INPUT", "e89d7e09-aa5f-5a71-b25c-47b0d220420d"),
    ("linkup_search_tool", "exclude_domains", "INPUT", "097964fe-fe14-5054-94d7-c3fa72b83461"),
    ("linkup_search_tool", "output", "OUTPUT", "4c28f36e-ff98-59a9-b981-0bdaf587b52d"),
    ("linkup_search_tool", "sources", "OUTPUT", "3482cb80-ab41-588d-a8ed-0ecb2d349886"),
    # Web Search OpenAI Tool
    ("web_search_openai_agent_v2", "query", "INPUT", "afb53ca9-3182-5539-805a-63678a36c9f6"),
    ("web_search_openai_agent_v2", "messages", "INPUT", "83748dd6-05a8-5025-bbf7-3136ebb66648"),
    ("web_search_openai_agent_v2", "filters", "INPUT", "a37deb89-0c4d-5a34-9053-fb43d9bb26d9"),
    ("web_search_openai_agent_v2", "output", "OUTPUT", "01e1c83a-68ff-53fc-8a73-efc1f348efcb"),
    # HubSpot MCP Tool
    ("hubspot_mcp_tool", "tool_name", "INPUT", "e9841a9a-892b-5f11-bbf7-9e519ffe121b"),
    ("hubspot_mcp_tool", "tool_arguments", "INPUT", "16a055d3-0ba0-5983-9cfb-3e14075fc646"),
    ("hubspot_mcp_tool", "output", "OUTPUT", "b538051c-ea50-579f-bd43-e6a2b8a7de87"),
    ("hubspot_mcp_tool", "content", "OUTPUT", "fd8cdef2-6f27-54c1-81ea-6bc71f151d7f"),
    ("hubspot_mcp_tool", "is_error", "OUTPUT", "ca4de86c-7e45-5dab-9876-3fa3fbf39e49"),
    # Docx Template
    ("docx_template_agent", "template_input_path", "INPUT", "744d7704-64b5-5884-8920-e3eefbebcf61"),
    ("docx_template_agent", "template_information_brief", "INPUT", "5b2e4057-f881-50c6-99de-7684c1aad6d4"),
    ("docx_template_agent", "output_filename", "INPUT", "87f84b5d-cbbc-5b45-a8ec-b4e28b7c0839"),
    ("docx_template_agent", "output", "OUTPUT", "4ef25fb8-2cc1-509d-88d4-b09ca533da89"),
    ("docx_template_agent", "artifacts", "OUTPUT", "e5a7a66a-3318-5e74-b07c-92e68f451917"),
    # Remote MCP Tool (shared schema)
    ("remote_mcp_tool", "tool_name", "INPUT", "6c515120-4349-58ed-817d-7f48fe372a23"),
    ("remote_mcp_tool", "tool_arguments", "INPUT", "d6285373-043a-5b39-9e08-c385885962c2"),
    ("remote_mcp_tool", "output", "OUTPUT", "d18788ea-f921-5e0e-9176-10ffbc1d2ae9"),
    ("remote_mcp_tool", "content", "OUTPUT", "4cb6dcda-c857-5434-9240-0f481f947beb"),
    ("remote_mcp_tool", "is_error", "OUTPUT", "6b0554e2-9e82-5b39-98dc-698e5d8e0861"),
]


def _migrate_port_definition_id(
    connection,
    component_version_id: str,
    port_name: str,
    port_type: str,
    new_port_def_id: str,
) -> None:
    """Replace port_definition id for (component_version_id, name, port_type).
    Copies row to new id, updates all FKs, deletes old row.
    """
    result = connection.execute(
        sa.text(
            """
            SELECT id FROM port_definitions
            WHERE component_version_id = :cv_id
              AND name = :name
              AND port_type = :port_type
            """
        ),
        {"cv_id": component_version_id, "name": port_name, "port_type": port_type},
    )
    row = result.fetchone()
    if not row:
        return  # Port not seeded yet, nothing to migrate
    old_id = str(row[0])
    if old_id == new_port_def_id:
        return  # Already migrated

    # Insert new row with fixed id (same data)
    connection.execute(
        sa.text(
            """
            INSERT INTO port_definitions (
                id, component_version_id, name, port_type, is_canonical,
                description, parameter_type, ui_component, ui_component_properties,
                nullable, "default", is_tool_input, is_advanced
            )
            SELECT
                :new_id, component_version_id, name, port_type, is_canonical,
                description, parameter_type, ui_component, ui_component_properties,
                nullable, "default", is_tool_input, is_advanced
            FROM port_definitions
            WHERE id = :old_id
            """
        ),
        {"new_id": new_port_def_id, "old_id": old_id},
    )

    # Update FKs that reference the old id
    connection.execute(
        sa.text(
            "UPDATE input_port_instances SET port_definition_id = :new_id WHERE port_definition_id = :old_id"
        ),
        {"new_id": new_port_def_id, "old_id": old_id},
    )
    connection.execute(
        sa.text(
            "UPDATE port_mappings SET source_port_definition_id = :new_id WHERE source_port_definition_id = :old_id"
        ),
        {"new_id": new_port_def_id, "old_id": old_id},
    )
    connection.execute(
        sa.text(
            "UPDATE port_mappings SET target_port_definition_id = :new_id WHERE target_port_definition_id = :old_id"
        ),
        {"new_id": new_port_def_id, "old_id": old_id},
    )

    # Remove old row
    connection.execute(sa.text("DELETE FROM port_definitions WHERE id = :old_id"), {"old_id": old_id})


def upgrade() -> None:
    connection = op.get_bind()
    for cv_key, port_name, port_type, new_id in PORT_MIGRATIONS:
        component_version_id = CV.get(cv_key)
        if not component_version_id:
            continue
        _migrate_port_definition_id(
            connection,
            component_version_id,
            port_name,
            port_type,
            new_id,
        )


def downgrade() -> None:
    # Reverting would require restoring the previous random IDs and all FKs; we don't have them.
    # Downgrade is a no-op: fixed IDs remain. Re-run seed to recreate ports if needed.
    pass
