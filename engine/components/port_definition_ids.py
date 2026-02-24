"""Explicit UUID for each port definition (input/output) in engine components.

One constant per port. Renaming a schema or field does not change the ID.
Used in engine Field json_schema_extra and in migrations when needed.
"""

from uuid import UUID

# ---------------------------------------------------------------------------
# LLM Call (output_format ID is fixed by migration b3c4d5e6f7a8)
# ---------------------------------------------------------------------------
LLMCallInputs_MESSAGES = UUID("c0d4a691-804b-55eb-bb8c-f60de6f58cea")
LLMCallInputs_PROMPT_TEMPLATE = UUID("a5ce402b-219f-5a4b-aeef-05e608c8094f")
LLMCallInputs_OUTPUT_FORMAT = UUID("b2c3d4e5-f6a7-4789-8012-3456789abcde")  # migration fixed
LLMCallOutputs_OUTPUT = UUID("243e6363-7e2b-581e-9c7f-392a2a22f053")
LLMCallOutputs_ARTIFACTS = UUID("1448a2b3-abe8-5d0d-ac59-73d7a74468b3")

# ---------------------------------------------------------------------------
# AI Agent (output_format ID is fixed by migration b3c4d5e6f7a8)
# ---------------------------------------------------------------------------
AIAgentInputs_MESSAGES = UUID("9cd1d16c-88ce-56e9-ace4-fda9d208fdcb")
AIAgentInputs_INITIAL_PROMPT = UUID("90089d14-2bbc-5224-868f-5e8d00084431")
AIAgentInputs_OUTPUT_FORMAT = UUID("c3d4e5f6-a7b8-4901-9012-3456789abcdf")  # migration fixed
AIAgentOutputs_OUTPUT = UUID("fe81e36c-fb8d-5500-ba41-3f5b1be1be09")
AIAgentOutputs_FULL_MESSAGE = UUID("2a224fdf-7e4d-5b4e-9a7b-660e16739bb5")
AIAgentOutputs_IS_FINAL = UUID("3c31134a-59f6-57e2-bd3b-a78dbc3ad343")
AIAgentOutputs_ARTIFACTS = UUID("645cbf1d-2716-54db-a5f1-0a01d663795f")

# ---------------------------------------------------------------------------
# Static Responder
# ---------------------------------------------------------------------------
StaticResponderInputs_INPUT = UUID("dadb9596-3514-5ac3-bf43-39e2faaa10b5")
StaticResponderOutputs_INPUT_FROM_PREVIOUS = UUID("9f5a40be-1c4c-530c-b6b9-ec8d6b328aa4")
StaticResponderOutputs_STATIC_MESSAGE = UUID("892cc8e6-c0b9-5448-a8e5-c3bb1c31223e")

# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------
FilterInputs_MESSAGES = UUID("01ebc4de-90bf-52d8-a2ef-3327b42c1375")
FilterInputs_ERROR = UUID("405fcd4f-7940-5e73-81df-c3028fbe98fa")
FilterInputs_ARTIFACTS = UUID("ea6ef52d-074a-55ae-ace4-68dd928a2126")
FilterInputs_IS_FINAL = UUID("b4a87161-25ab-5552-9320-f9ee25744134")
FilterOutputs_OUTPUT = UUID("caad74c0-db46-5547-bd17-4002381f1699")
FilterOutputs_IS_FINAL = UUID("261b08d8-9aba-5db3-94e7-4b5370c5dd29")
FilterOutputs_ARTIFACTS = UUID("cfa90f8e-0aa9-5840-932c-98d911d1c388")

# ---------------------------------------------------------------------------
# If/Else
# ---------------------------------------------------------------------------
IfElseInputs_CONDITIONS = UUID("561890ca-d8f8-59eb-8f5c-740d255f5bf3")
IfElseInputs_OUTPUT_VALUE_IF_TRUE = UUID("d0fc1698-9135-53b5-923e-4aad1af48e65")
IfElseOutputs_RESULT = UUID("fd7070e4-3b00-59db-be96-4a78f8e5108a")
IfElseOutputs_OUTPUT = UUID("14d060e8-e868-53b9-8770-7c5db070bbe5")
IfElseOutputs_SHOULD_HALT = UUID("e27c22d3-c147-5023-ad88-93c8e0b78917")

# ---------------------------------------------------------------------------
# Table Lookup
# ---------------------------------------------------------------------------
TableLookupInputs_LOOKUP_KEY = UUID("f54f38dd-5296-568b-bdd1-f60240842798")
TableLookupOutputs_LOOKUP_VALUE = UUID("04bd46e1-46b6-51bb-b4cd-453bb137040f")

# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------
RAGInputs_QUERY_TEXT = UUID("15925ea7-1ce5-5054-bce2-6811cb7376d6")
RAGInputs_FILTERS = UUID("13d8c92c-ab62-5213-b902-3faa3b47b00c")
RAGOutputs_OUTPUT = UUID("eb1f374b-d9fc-57b5-91da-6960662b79a5")
RAGOutputs_IS_FINAL = UUID("7ad047d9-c8c1-54f9-adf6-a282c37d8ba5")
RAGOutputs_ARTIFACTS = UUID("167ee096-2d0d-5d6b-9bca-7f10a2e598ba")

# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------
RetrieverInputs_QUERY = UUID("e7d48658-5d40-5477-8ab2-426be7de14f1")
RetrieverInputs_FILTERS = UUID("9c9afb0a-25c1-5e39-a04d-b92dbcd76011")
RetrieverOutputs_FORMATTED_CONTENT = UUID("ac5ff0e7-d546-5377-a8ba-0e37e43f7335")
RetrieverOutputs_ARTIFACTS = UUID("5414eb01-a237-58f1-8536-e1b0a04ade0d")

# ---------------------------------------------------------------------------
# Terminal Command Runner
# ---------------------------------------------------------------------------
TerminalCommandRunnerToolInputs_COMMAND = UUID("94c477b0-42fe-5fed-9302-49081cfd8249")
TerminalCommandRunnerToolOutputs_OUTPUT = UUID("bd047f71-760f-5a74-afef-3deeb27126bc")
TerminalCommandRunnerToolOutputs_ARTIFACTS = UUID("5fe72a50-0d97-5aed-8084-ff4ecf471b7e")

# ---------------------------------------------------------------------------
# Python Code Runner
# ---------------------------------------------------------------------------
PythonCodeRunnerToolInputs_PYTHON_CODE = UUID("91259a1e-9d35-50e0-b1c9-622039bb56c3")
PythonCodeRunnerToolInputs_INPUT_FILEPATHS = UUID("d95ef69d-05a4-53d3-9e2e-80775c8e7ea5")
PythonCodeRunnerToolOutputs_OUTPUT = UUID("42f0840d-8025-5168-bc2b-59172d26a6a7")
PythonCodeRunnerToolOutputs_ARTIFACTS = UUID("17c2328f-b775-5b08-be82-3e91f2f24ff6")

# ---------------------------------------------------------------------------
# PDF Generation Tool
# ---------------------------------------------------------------------------
PDFGenerationToolInputs_MARKDOWN_CONTENT = UUID("bf5232e1-4b1f-5e54-9edd-20bcd7f70ded")
PDFGenerationToolInputs_FILENAME = UUID("9dfdc9ea-7a11-52ed-afce-95fc048c16e9")
PDFGenerationToolOutputs_OUTPUT_MESSAGE = UUID("c6e29894-0016-52c5-84c9-07822f7d4b33")
PDFGenerationToolOutputs_ARTIFACTS = UUID("966fd293-494b-5243-bf5e-f33762b81636")

# ---------------------------------------------------------------------------
# DOCX Generation Tool
# ---------------------------------------------------------------------------
DOCXGenerationToolInputs_MARKDOWN_CONTENT = UUID("1c8f7960-2ea7-5f06-a890-c47fa67e2ea5")
DOCXGenerationToolInputs_FILENAME = UUID("1a5434b2-9e7a-5541-82ff-8e114d83ac99")
DOCXGenerationToolOutputs_OUTPUT_MESSAGE = UUID("481c7d14-ee9b-54c9-8d6a-b0612d2de5ff")
DOCXGenerationToolOutputs_ARTIFACTS = UUID("874ec409-6826-5f86-a24e-c671b0d39fa0")

# ---------------------------------------------------------------------------
# Linkup Search Tool
# ---------------------------------------------------------------------------
LinkupSearchToolInputs_QUERY = UUID("a22b9583-3236-5860-9efc-00b37b11232d")
LinkupSearchToolInputs_DEPTH = UUID("c06fb129-e023-5c7a-a55f-82dec5b54c5b")
LinkupSearchToolInputs_FROM_DATE = UUID("d2408a80-1caf-5d20-a237-62b1e0bc1dab")
LinkupSearchToolInputs_TO_DATE = UUID("252376ed-93a3-5256-ae21-559cf720a606")
LinkupSearchToolInputs_INCLUDE_DOMAINS = UUID("e89d7e09-aa5f-5a71-b25c-47b0d220420d")
LinkupSearchToolInputs_EXCLUDE_DOMAINS = UUID("097964fe-fe14-5054-94d7-c3fa72b83461")
LinkupSearchToolOutputs_OUTPUT = UUID("4c28f36e-ff98-59a9-b981-0bdaf587b52d")
LinkupSearchToolOutputs_SOURCES = UUID("3482cb80-ab41-588d-a8ed-0ecb2d349886")

# ---------------------------------------------------------------------------
# Web Search OpenAI Tool
# ---------------------------------------------------------------------------
WebSearchOpenAIToolInputs_QUERY = UUID("afb53ca9-3182-5539-805a-63678a36c9f6")
WebSearchOpenAIToolInputs_MESSAGES = UUID("83748dd6-05a8-5025-bbf7-3136ebb66648")
WebSearchOpenAIToolInputs_FILTERS = UUID("a37deb89-0c4d-5a34-9053-fb43d9bb26d9")
WebSearchOpenAIToolOutputs_OUTPUT = UUID("01e1c83a-68ff-53fc-8a73-efc1f348efcb")

# ---------------------------------------------------------------------------
# HubSpot MCP Tool
# ---------------------------------------------------------------------------
HubSpotMCPToolInputs_TOOL_NAME = UUID("e9841a9a-892b-5f11-bbf7-9e519ffe121b")
HubSpotMCPToolInputs_TOOL_ARGUMENTS = UUID("16a055d3-0ba0-5983-9cfb-3e14075fc646")
HubSpotMCPToolOutputs_OUTPUT = UUID("b538051c-ea50-579f-bd43-e6a2b8a7de87")
HubSpotMCPToolOutputs_CONTENT = UUID("fd8cdef2-6f27-54c1-81ea-6bc71f151d7f")
HubSpotMCPToolOutputs_IS_ERROR = UUID("ca4de86c-7e45-5dab-9876-3fa3fbf39e49")

# ---------------------------------------------------------------------------
# Docx Template
# ---------------------------------------------------------------------------
DocxTemplateInputs_TEMPLATE_INPUT_PATH = UUID("744d7704-64b5-5884-8920-e3eefbebcf61")
DocxTemplateInputs_TEMPLATE_INFORMATION_BRIEF = UUID("5b2e4057-f881-50c6-99de-7684c1aad6d4")
DocxTemplateInputs_OUTPUT_FILENAME = UUID("87f84b5d-cbbc-5b45-a8ec-b4e28b7c0839")
DocxTemplateOutputs_OUTPUT = UUID("4ef25fb8-2cc1-509d-88d4-b09ca533da89")
DocxTemplateOutputs_ARTIFACTS = UUID("e5a7a66a-3318-5e74-b07c-92e68f451917")

# ---------------------------------------------------------------------------
# MCP Tool (shared by Local and Remote MCP)
# ---------------------------------------------------------------------------
MCPToolInputs_TOOL_NAME = UUID("6c515120-4349-58ed-817d-7f48fe372a23")
MCPToolInputs_TOOL_ARGUMENTS = UUID("d6285373-043a-5b39-9e08-c385885962c2")
MCPToolOutputs_OUTPUT = UUID("d18788ea-f921-5e0e-9176-10ffbc1d2ae9")
MCPToolOutputs_CONTENT = UUID("4cb6dcda-c857-5434-9240-0f481f947beb")
MCPToolOutputs_IS_ERROR = UUID("6b0554e2-9e82-5b39-98dc-698e5d8e0861")
