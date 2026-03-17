"""Domain-specific documentation exposed as MCP resources and a fallback tool.

Each domain guide is a markdown string registered as a `docs://{domain}` resource.
The AI fetches only the domain it needs, keeping base context minimal.
The `get_guide` tool provides the same content for clients that don't support resources.
"""

from fastmcp import FastMCP

GETTING_STARTED = """\
# Getting Started

## Connection

The MCP endpoint is `https://mcp.draftnrun.com/mcp` (Streamable HTTP).

- **Cursor**: add `{"mcpServers":{"draftnrun":{"url":"https://mcp.draftnrun.com/mcp"}}}` to `.cursor/mcp.json`.
- **Claude Desktop**: add \
`{"mcpServers":{"draftnrun":{"type":"http","url":"https://mcp.draftnrun.com/mcp"}}}` \
to `claude_desktop_config.json`. The `"type":"http"` field is required.

Authentication is handled via OAuth 2.1 PKCE with Supabase — the client starts the flow \
automatically on first connection.

## First Steps — Always Do This

Before any operation, set an organization context:

1. `list_my_organizations` — see available orgs and your role in each
2. `select_organization(organization_id)` — set the active org for the session \
(caches role + release stage)
3. `get_current_context` — verify active org, role, release_stage, user info

All org-scoped tools will fail with "No organization selected" until you do this.

## Role Hierarchy

`SUPER_ADMIN > ADMIN > DEVELOPER > MEMBER`

- **Member**: read-only access (list, get)
- **Developer**: create/update/delete resources, run graphs, manage cron jobs, OAuth connections, knowledge mutations
- **Admin**: manage variables, secrets, invite members
- **SuperAdmin**: org limits, cost management

If a tool returns a role error, check with `get_current_context`.

## Key Concepts

- **Agent vs Workflow**: Agents are configured via `configure_agent`/`add_tool_to_agent` \
(high-level). Workflows use `get_graph`/`update_graph` (low-level DAG manipulation).
- **Draft vs Production**: Only drafts are editable. Use `save_graph_version` to snapshot, \
`publish_to_production` to go live.
- **Release Stage**: Org-level tier (public/early_access/beta/internal) controlling which \
components are visible.
- **RBAC**: Variables/secrets require admin. Deletions require developer+. Invites require admin in the target org.

## AI Builder Habits

- Never copy IDs, instance UUIDs, component IDs, source IDs, or graph JSON from another \
project/org as a shortcut. Always inspect the current org/project first with `list_*`, \
`get_project_overview`, `get_graph`, `list_components`, and `search_components`.
- Ask clarifying questions before making architecture choices that affect edge cases, file \
lifecycle, retries, routing, fallbacks, or user-visible behavior.
- Ask for explicit user permission before destructive or external-account actions: publish, \
delete, revoke OAuth, rotate/revoke keys, or guiding OAuth connection setup in the web UI.
- Prefer dedicated components over generic code. Use search, RAG, integration, file, and \
document components when available. Use `python_code_runner` or \
`terminal_command_runner` only for small, bounded transformations or glue work when no \
dedicated component fits.
- Treat `_truncated: true` responses as incomplete data. Do not infer missing graph fields, \
document content, or file outputs.

## Important Constraints

- `list_runs` caps `page_size` at 100
- `get_org_charts` and `get_org_kpis` clamp `duration` to 1–365 days
- Batch deletions: `delete_datasets`, `delete_entries`, `delete_judges` accept lists of IDs
- Graph updates send the full graph structure — always `get_graph` first, modify, then `update_graph`
- Secrets values are write-only; `list_secrets` returns masked values
- OAuth connections must be set up in the web UI with explicit user permission — use \
`check_oauth_status` to verify
- Fetch `docs://versioning` before saving, publishing, scheduling, or reasoning about live vs editable versions
- Fetch `docs://file-management` before mutating knowledge documents or building file-centric workflows
"""

AGENT_CONFIG = """\
# Agent Configuration

## Create and Configure an Agent

1. `create_agent(name, description)` → auto-generates ID, icon, color (requires developer role)
2. `get_project_overview(project_id)` → confirm the editable draft runner
3. **Discover available models** — call `get_graph(project_id, graph_runner_id)` and inspect the \
`completion_model` parameter's `ui_component_properties.options` list.
4. `configure_agent(agent_id, graph_runner_id, system_prompt=..., model=<model from step 3>)`
5. **Discover available tools** — call `search_components(query)` to find the exact component \
display name.
6. `add_tool_to_agent(agent_id, graph_runner_id, "<display name from step 5>")` → adds by name
7. `run_agent(project_id, graph_runner_id, [{"role": "user", "content": "test"}])` → test it
8. `save_graph_version(project_id, graph_runner_id)` → snapshot
9. `publish_to_production(project_id, graph_runner_id)` → go live

## configure_agent

Sets system prompt and existing model parameters on the agent's root AI Agent node. It handles the \
full read-modify-write cycle internally — you only pass what you want to change.

Model names are auto-prefixed when no provider is specified: `"gpt-4.1"` becomes `"openai:gpt-4.1"`. \
Pass `"anthropic:claude-sonnet-4-5"` for non-OpenAI models.

### Model selection — NEVER invent model names

**Do NOT guess or hard-code model names.** Models are deprecated and removed regularly; names you \
remember from training data may no longer exist.

Safe workflow:
1. Call `get_graph(project_id, graph_runner_id)`.
2. Find the `completion_model` parameter in the root AI Agent node's `parameters` list.
3. Read its `ui_component_properties.options` — each entry has `value` (the identifier to pass) \
and `label` (human-readable name).
4. Pick a `value` from that list and pass it as the `model` argument.

`configure_agent` validates the model against the available options and raises a clear error with \
the full list if the model is not found.

Important constraint: this helper merges into the agent's current `model_parameters`. It does not \
invent parameters that are not already present in the backend response.

## add_tool_to_agent / remove_tool_from_agent

Add or remove tools by **component display name** — the `name` value returned by \
`search_components()`.

Examples: `"Internet Search (Linkup)"`, `"Internet Search (OpenAI)"`, `"Knowledge Search (Retriever)"`.

Matching is case-insensitive.  Always call `search_components(query)` first to discover the exact \
name — do NOT guess component names from memory.

Guardrails:

- Only `function_callable` components are valid agent tools.
- The MCP helper should be treated as one-tool-per-component, matching the frontend selection UI.
- Integration-backed / OAuth-backed components may require an integration relationship that this \
helper cannot create automatically.

Pass `tool_parameters` to override default parameter values when adding.

## Tool Selection Habits

- For web research, prefer dedicated search components (use `search_components("search")` to \
discover them) instead of building custom search flows in code.
- Use `python_code_runner` and `terminal_command_runner` only for small, bounded tasks such as \
formatting, parsing, or deterministic CLI glue.
- If the required component is not visible in `list_components()` for the active org, treat it \
as unavailable instead of designing around it from memory.
- Fetch `docs://integrations` before adding Gmail, Slack, HubSpot, or other integration-backed tools.

## Quick Orientation

`get_project_overview(project_id)` returns the draft/production runners, recent runs, and safety \
hints in one call.
"""

GRAPHS = """\
# Graph Editing

Fetch `docs://versioning` before editing, saving, or publishing graphs.

A graph is a DAG with four top-level collections:

```json
{
  "component_instances": [...],   // nodes
  "edges": [...],                 // execution flow (A runs before B)
  "port_mappings": [...],         // explicit non-canonical data flow
  "relationships": [...],         // parent-child nesting (agent → tools)
  "playground_input_schema": {},  // Start node payload defaults
  "playground_field_types": {}    // playground field UI classification
}
```

## Component Instance (node)

```json
{
  "id": "uuid",
  "name": "My LLM Call",
  "ref": "llm_1",
  "is_start_node": false,
  "component_id": "uuid",
  "component_version_id": "uuid",
  "component_name": "llm_call",
  "parameters": [
    {"name": "prompt", "kind": "parameter", "value": "You are a helpful assistant..."}
  ],
  "input_port_instances": [
    {
      "name": "messages",
      "field_expression": {
        "expression_json": {"type": "ref", "instance": "<uuid>", "port": "messages"}
      }
    }
  ]
}
```

Key fields:
- `ref` — human-readable label (display only, not used in expressions)
- `component_id` + `component_version_id` — which catalog component this is
- `parameters` — configured values (prompt, model, temperature, etc.)
- `input_port_instances` — input ports with their data sources (field expressions)

## Edges (execution order)

```json
{"id": "uuid", "origin": "node-uuid-A", "destination": "node-uuid-B", "order": 0}
```

Edge `id` can be `null` — the MCP layer auto-generates a UUID before sending to the backend \
(same as component instances). You can also provide your own UUID.

Always create an edge between sequential nodes — the engine uses topological sort on edges.

### Auto-canonical port mapping — edges are enough

When you create an edge, the backend auto-generates a `PortMapping` row using the \
`is_canonical` flag on each component's port definitions: \
`source.canonical_output → target.canonical_input`. This happens at save time in \
`_ensure_port_mappings_for_edges`.

| Component | Canonical output | Canonical input |
|-----------|-----------------|-----------------|
| Start (v2) | `messages` | — |
| AI Agent | `output` | `messages` |
| AI (LLM Call) | `output` | `messages` |
| Internet Search (Linkup) | `output` | `query` |
| PDF Generation | `output_message` | `markdown_content` |
| Gmail Sender | `status` | `mail_body` |
| Code Execution | `output` | `python_code` |

**Do NOT inject `input_port_instances` or field expressions for canonical inputs.** \
The frontend never does this — it relies entirely on the backend auto-generated PortMapping \
from the edge. The MCP must behave identically: just create the edge, the backend handles \
the data routing. Adding redundant `input_port_instances` entries for canonical ports creates \
inconsistency with the frontend behavior.

`input_port_instances` are for **non-canonical** wiring only (concat expressions, key \
extraction, cross-references to non-adjacent nodes, etc.).

### Field expressions override port mappings

When both an auto-mapped port mapping and a field expression target the same input port, \
the field expression wins.

### Readonly inputs — `messages` is auto-filled, never wire it manually

The `messages` input on AI Agent, AI (LLM Call), and Internet Search (OpenAI) is **readonly**. \
It is automatically populated from the previous component's canonical output via the edge. \
The frontend blocks editing this field; the MCP enforces the same constraint by stripping \
any `input_port_instances` or `kind="input"` parameter targeting `messages` on a node that \
has an incoming edge.

**Do not** write field expressions into `messages`. Instead, use `initial_prompt` to inject \
context into the agent's system prompt. The `initial_prompt` parameter accepts field expressions \
(concat, ref, literal) so you can combine static instructions with dynamic data from other nodes:

```json
{
  "name": "initial_prompt",
  "kind": "input",
  "value": null,
  "input_port_instances": [{
    "name": "initial_prompt",
    "field_expression": {
      "expression_json": {
        "type": "concat",
        "parts": [
          {"type": "literal", "value": "You are a research agent.\\n\\nPerson: "},
          {"type": "ref", "instance": "<start-uuid>", "port": "full_name"},
          {"type": "literal", "value": "\\nLinkedIn: "},
          {"type": "ref", "instance": "<start-uuid>", "port": "linkedin_url"}
        ]
      }
    }
  }]
}
```

The user's message flows naturally through `messages` via the edge. The agent combines both to \
produce its response.

### When to provide explicit port mappings

Provide explicit `port_mappings` when you need non-canonical wiring (for example mapping \
`output` to `mail_subject` instead of the canonical `mail_body`).

Important quirk: pure `port_mappings`-only edits are risky because current graph change detection \
excludes `port_mappings`. See `docs://known-quirks`.

## Port Mapping (data flow)

```json
{
  "source_instance_id": "node-uuid-A",
  "source_port_name": "output",
  "target_instance_id": "node-uuid-B",
  "target_port_name": "messages",
  "dispatch_strategy": "direct"
}
```

Distinct from edges — edges say "run B after A", port mappings say "send A's output to B's input".

## Relationship (nesting)

```json
{
  "parent_component_instance_id": "agent-uuid",
  "child_component_instance_id": "tool-uuid",
  "parameter_name": "tools",
  "order": 0
}
```

Used for agent nodes that contain tool sub-components.

## Updating a Graph

`update_graph` sends the full graph structure for the selected runner. The safe pattern:

1. `get_project_overview(project_id)` — identify the editable draft runner
2. `get_graph(project_id, graph_runner_id)` — get current state
3. Modify the response (add/remove nodes, change parameters, rewire ports)
4. `update_graph(project_id, graph_runner_id, modified_graph)` — send it back

For new component instances you have two options:

1. **`id: null`** — the MCP layer auto-generates a UUID before sending to the backend.
2. **Provide your own UUID** — recommended when other parts of the same payload reference \
the new node (edges, relationships, field expressions). Generate a fresh UUID client-side \
and use it consistently across the payload.

For existing nodes, include their current `id` from `get_graph`.

### Critical: always use current instance IDs

After `publish_to_production`, the backend creates a fresh draft with remapped instance UUIDs. \
Always call `get_graph` on the returned new draft before further edits.

After `save_graph_version`, the current draft stays editable and its instance IDs stay the same.

### Input data wiring: `kind="input"` vs `input_port_instances`

Two ways to wire data into a node's input ports:

1. **`kind="input"` parameters** — string values parsed into field expressions. Simple refs \
like `@{{uuid.port}}` can also create save-time port mappings for validation.
2. **`input_port_instances`** — JSON expression objects stored directly. No automatic save-time \
port mapping validation.

Use `kind="input"` for most literal values and simple references between type-compatible ports.

Use `input_port_instances` when:

- you need `json_build` or `concat`
- you need explicit expression JSON
- you are using key-extraction refs like `@{{uuid.port::key}}`

Reason: key-extraction refs are a backend special case. `kind="input"` skips automatic port mapping \
creation for `::key` refs to avoid false type-coercion errors.

**Priority rule**: if a field name is present in both `input_port_instances` and a `kind="input"` \
parameter, the `input_port_instances` version wins.

### Parameter `kind` is critical in `update_graph`

Every parameter should include an explicit `kind`:

- **`kind: "input"`** — treated as a field-expression-driven input
- **`kind: "parameter"`** — treated as a normal config parameter

If you omit `kind`, the backend defaults to `"parameter"`, which can fail validation for \
input-like fields.

### Required fields in `update_graph` payloads

Component instances require: `id`, `component_id`, `component_version_id`, `name`, `ref`, \
`is_start_node`, `parameters`, and `input_port_instances`.

Include `integration` on components that use OAuth or linked integrations (for example Gmail \
Sender) — omitting it can delete the linked integration relationship.

Edges require: `id` (use existing IDs from `get_graph`, generate new UUIDs, or pass `null` \
for auto-generation), `origin`, `destination`, and `order`.

## Field Expressions

Field expressions define how data flows into input ports:

| Type | JSON |
|------|------|
| Reference `@{{uuid.port}}` | `{"type": "ref", "instance": "<uuid>", "port": "name"}` |
| Key extraction `@{{uuid.port::key}}` | `{"type": "ref", "instance": "<uuid>", "port": "name", "key": "key"}` |
| Variable `@{{var_name}}` | `{"type": "var", "name": "var_name"}` |
| Literal (plain text) | `{"type": "literal", "value": "text"}` |
| Concatenation | `{"type": "concat", "parts": [...]}` |
| JSON build | `{"type": "json_build", "template": {...}, "refs": {...}}` |

**IMPORTANT**: The `instance` field in field expressions **must be the component instance UUID** \
(the `id` field from the component instance), **not** the human-readable `ref` name. The `ref` \
field is a display label only — using it in expressions produces a 400 error: \
`"Invalid referenced instance id in expression: '<ref>' is not a UUID"`.

Example — correct field expression referencing node output:

```json
{"type": "ref", "instance": "df934e83-1a31-487f-8977-a0614c6a76f1", "port": "output"}
```

Example — key extraction from an artifacts port:

```json
{"type": "ref", "instance": "df934e83-1a31-487f-8977-a0614c6a76f1", "port": "artifacts", "key": "pdf_filename"}
```

The string shorthand `@{{<uuid>.port}}` and `@{{<uuid>.port::key}}` follow the same rule — \
always use the instance UUID, never the `ref`.

### Runtime edge augmentation

The engine auto-adds edges from field expression references. A node referencing another node's \
output will always run after it, even without an explicit edge. Still create explicit edges — \
auto-augmentation is a safety net, not the primary design pattern.
"""

COMPONENTS = """\
# Component Catalog

Use `list_components()` for the full catalog (auto-filtered by org release stage) or \
`search_components(query)` for targeted lookup. Blank or whitespace-only search queries are rejected.

## Component Naming

Components are identified by their **display name** (the `name` field in catalog responses). \
Always use `search_components(query)` to discover the exact display name before passing it \
to `add_tool_to_agent()` — do NOT hard-code names from memory; they change over time.

## Available Component Types (indicative — always verify with search_components)

**AI**: AI Agent, AI (LLM Call), Categorizer

**Workflow Logic**: Start, Filter, If/Else, Router, Project Reference, \
Chunk Processor, Static Responder, Table Lookup

**RAG**: RAG Agent, Hybrid RAG Agent, Knowledge Search (Retriever), Retriever Tool, \
Synthesizer, Hybrid Synthesizer, Relevant Chunk Selector, Cohere Reranker, \
Formatter, Vocabulary Search, Document Search

**Search**: Internet Search (OpenAI), Internet Search (Linkup)

**SQL/Data**: SQL Tool, React SQL Agent, Run SQL Query Tool, \
SQL DB Service, Snowflake DB Service

**Integrations**: Gmail Sender, Slack Sender, HubSpot MCP Tool, \
Remote MCP Tool, API Call Tool

**Code**: Python Code Runner, Terminal Command Runner

**Files**: PDF Generation, DOCX Generation, DOCX Template

**Documents**: OCR Call, Document Enhanced LLM Call, Document React Loader Agent

## Selection Guardrails

- `list_components()` and `search_components()` are filtered by the org's release stage \
(public, early_access, beta, internal). Some components (e.g. `pdf_generation`, `docx_generation`) \
are only visible in orgs with higher release stages. If the catalog call fails with a permission \
error, try a different org or check the org's release stage with `get_current_context()`.
- Always call `list_components()` or `search_components()` in the active org before designing a \
workflow. Release stage filters apply; do not hard-code components from memory or from another project.
- Prefer dedicated search components for web research and dedicated document/file components for \
OCR, retrieval, or file generation when available.
- Use `python_code_runner` or `terminal_command_runner` only for small, bounded transformations \
or CLI glue.
- Do not assume internal/beta file or document components are available. If a component is not \
in the catalog response, treat it as unavailable.
- Fetch `docs://file-management` before building workflows that ingest files, mutate knowledge \
documents, or expect downloadable generated files.

## Parameter Types

`string`, `integer`, `float`, `boolean`, `json`, `component`, `tool`, `data_source`, \
`secrets`, `llm_api_key`, `llm_model`

## Port Types

Ports are `INPUT` or `OUTPUT`. Each component has:
- **Canonical ports** — the default input/output (e.g., `messages` in/out for LLM calls)
- **Dynamic ports** — created at runtime based on configuration (e.g., Start node creates \
output ports from `payload_schema` keys)

### Port Discovery

Use `search_components(query)` to discover port names — the response includes `input_ports` \
and `output_ports` for each matching component, with a `canonical: true` flag on default ports.

### Common Component Port Names

| Component | Output Ports | Input Ports | Notes |
|-----------|-------------|-------------|-------|
| Start (v2) | `messages`, + dynamic from `payload_schema` | — | Dynamic ports match `payload_schema` keys |
| AI Agent | `output` | `messages` (readonly, auto-filled) | Use `initial_prompt` for context injection |
| AI (LLM Call) | `output` | `messages` (readonly, auto-filled) | |
| PDF Generation | `output_message`, `artifacts` | `markdown_content` | `@{{uuid.artifacts::pdf_filename}}` |
| Gmail Sender | `status` | `mail_body`, `mail_subject`, `recipients` | |
| Slack Sender | `status` | `message`, `channel` | |
| Internet Search (Linkup) | `output` | `query` | |
| Code Execution | `output` | `python_code` | |

Port names marked as canonical are auto-wired by the backend when an edge is created — see \
`docs://graphs` for the canonical port mapping table.
"""

EXECUTION = """\
# Running Agents & Payloads

Fetch `docs://playground` for runner-selection and UI execution habits.

## MCP Execution Surface

`run_agent(project_id, graph_runner_id, messages, timeout=60)` — fires an async run, \
auto-polls for completion, and returns the final result in one call.

The `run_agent` tool exposes only the `messages` argument. It does **not** expose:

- arbitrary Start-node payload fields
- a `response_format` selector
- a generic file upload helper

It sends only:

```json
{
  "messages": [{"role": "user", "content": "Hello"}]
}
```

If a workflow expects additional Start fields, configure them in the graph or use a backend/API \
surface outside this MCP.

Response:

```json
{
  "message": "The agent's text response",
  "artifacts": {"key": "value"},
  "trace_id": "for-debugging",
  "files": [{"filename": "report.pdf", "content_type": "application/pdf", "s3_key": "temp-files/..."}],
  "error": null
}
```

- Generated files usually come back as `files[].s3_key` because the async endpoint forces \
`ResponseFormat.S3_KEY`.
- There is currently no MCP tool to download file bytes from those keys.
- Large run results may be returned as `_truncated` / `partial_data` by the MCP client.

## Inspect a Run

1. `list_runs(project_id)` → find the run
2. `get_run(project_id, run_id)` → status and metadata
3. `get_run_result(project_id, run_id)` → output data
4. `list_traces(project_id)` → find trace for debugging
5. `get_trace_tree(trace_id)` → full span tree with timings

## Debugging a Run

When a run completes but produces unexpected results (wrong output, empty data, tool errors), \
the most effective debugging path is:

1. `list_runs(project_id)` → find the run and extract its `trace_id`
2. `get_trace_tree(trace_id)` → inspect every span: LLM calls, tool invocations, exact \
inputs/outputs, and token counts

The trace tree reveals the exact tool calls the agent made and their responses — for example, \
an MCP tool returning empty results due to a wrong parameter value. This is far more useful \
than `get_run_result` alone, which only shows the final output.

## The Payload Concept

The Start node defines expected inputs via `payload_schema`:

```json
{"messages": [{"role": "user", "content": ""}], "company_name": "Acme Corp", "language": "en"}
```

At runtime:

1. schema defaults are loaded
2. runtime input overrides matching keys
3. `messages` is extracted for the execution pipeline
4. the remaining fields are injected into `ctx` and exposed as Start outputs

Additional execution semantics:

- `set_id` / `set_ids` are extracted before execution for variable resolution
- `conversation_id` is generated automatically if omitted
- the current MCP wrapper does not expose either of those fields directly

That backend concept is broader than the current MCP wrapper. From this MCP, only `messages` is \
directly exposed today.
"""

VARIABLES = """\
# Variables & Secrets

All variable tools require **admin** role.

## Variable Definitions

Variable definitions can be global or project-scoped:

1. `list_variable_definitions` → see all definitions
2. `upsert_variable_definition(name, definition)` → create/update
3. `delete_variable_definition(id)` → remove

Frontend behavior to mirror mentally:

- global definitions are available everywhere in the org
- project-scoped definitions are only visible to the projects they target

## Variable Sets

Named overrides for variable definitions (e.g., per-environment or per-client):

1. `list_variable_sets` → see all sets
2. `upsert_variable_set(name, values)` → create/update
3. `delete_variable_set(id)` → remove

## Secrets

Encrypted key-value pairs (API keys, credentials):

1. `list_secrets` → returns masked values
2. `upsert_secret(key, value)` → create/update (write-only)
3. `delete_secret(id)` → remove

## Resolution at Runtime

Variables are resolved in layers:

1. **Definition defaults** — from variable definitions
2. **Variable set overrides** — from `set_id`/`set_ids` passed at invocation (left-to-right, later wins)
3. **Secret variables** — decrypted at resolution time, never exposed in responses

Additional backend behavior:

- unknown set IDs are ignored rather than raising an error
- extra keys in a variable set that do not match definitions are ignored
- OAuth variable sets inject raw values directly

Field expressions with `@{{var_name}}` resolve against this merged dict.
"""

KNOWLEDGE = """\
# Knowledge Base

## Source Types

A source is an ingestion-backed collection used for RAG retrieval. Four types exist:

- **`website`** — crawls a URL with Firecrawl, follows links up to `max_depth`, caps at `limit` \
pages. **Creatable via MCP.**
- **`database`** — connects to an external database, reads rows from a table, indexes text \
columns as chunks. **Creatable via MCP.**
- **`local`** — ingests files uploaded through the web UI (stored in S3). Not arbitrary \
filesystem access. *Create via web UI only* (MCP has no file-upload tool yet).
- **`google_drive`** — ingests files from a Google Drive folder via OAuth. *Create via web UI \
only* (requires interactive OAuth flow).

## Source Tools

1. `create_source(source_type, config, name?)` — create a source and start ingestion \
(developer+ role). Supported types: `website`, `database`. The backend provisions \
infrastructure (DB table, Qdrant collection) automatically.
2. `list_sources` → existing sources in the active org
3. `update_source(source_id, source_data)` → re-trigger ingestion with the **stored** source \
definition. Does NOT accept config changes — `source_data` is ignored. To change config \
(URL, limit, etc.), use the web UI.
4. `delete_source(source_id)` → remove (developer+ role required)
5. `check_source_usage(source_id)` → which projects reference this source

### create_source config examples

Website: `create_source(source_type="website", config={"url": "https://example.com", \
"limit": 10, "max_depth": 2}, name="Example docs")`

Database: `create_source(source_type="database", config={"source_db_url": "postgresql://...", \
"source_table_name": "articles", "id_column_name": "id", \
"text_column_names": ["title", "body"]}, name="Articles DB")`

## Documents & Chunks

1. `list_documents(source_id)` → documents in a source
2. `get_document(source_id, document_id)` → document with chunks
3. `update_document_chunks(source_id, document_id, chunks)` → risky full replacement; requires developer role; \
requires explicit `confirm_full_replacement=True`
4. `delete_document(source_id, document_id)` → destructive; vector cleanup is not guaranteed

Documents are logical groups of ingested chunks, not guaranteed to be original binary files.
Chunks are managed at the document level (not individually).

Fetch `docs://file-management` and `docs://known-quirks` before mutating documents or designing \
file/document workflows.
"""

FILE_MANAGEMENT = """\
# File Management

## Scope

The current MCP surface is **not** a general file API. It can:

- inspect existing knowledge sources and logical documents
- run graphs with `messages`
- return references to some generated files

It does **not** currently expose a full upload/download workflow for arbitrary files.

## Knowledge Sources

Four source types exist. MCP can create `website` and `database` sources via `create_source`. \
For `local` (file upload) and `google_drive` (OAuth), use the web UI.

See `docs://knowledge` for full source type descriptions and `create_source` config examples.

### Source creation/update guardrails

- `create_source` supports `website` and `database` types (developer+ role). Infrastructure \
(DB table, Qdrant collection) is provisioned automatically by the backend.
- `list_sources` is the safest discovery tool.
- `update_source` re-triggers ingestion with the **stored** source definition. It does NOT \
accept config changes — `source_data` is ignored. To change config, use the web UI.
- The web product currently caps source uploads at 100 files and validates allowed file types \
based on `document_reading_mode`.

## Documents

A "document" is a logical group of ingested chunks, usually keyed by the underlying `file_id`.
It is not guaranteed to be the original binary file, and MCP does not currently provide a \
document download tool.

Safe tools:

- `list_documents`
- `get_document`

Risky mutation tools:

- `update_document_chunks` replaces chunks via a source-scoped sync. Do not use it as a routine \
partial edit API. The MCP tool is blocked by default unless you pass \
`confirm_full_replacement=True`.
- `delete_document` removes document rows from the ingestion DB, but vector cleanup is not \
guaranteed.

Only mutate documents when the user explicitly asks and the desired end state is fully known.

## Runtime Input Files

The backend can accept file-shaped payload values like:

```json
{"type": "file", "file": {"filename": "report.pdf", "file_data": "<base64>"}}
```

However, the MCP `run_agent` tool currently exposes only the `messages` argument. \
Do not claim the MCP has a general file upload helper.

The web playground allows file-style inputs with a 10 MB per-file limit, but that is a frontend \
behavior, not a current MCP capability.

## Generated Files

Some components can create files (for example PDF or DOCX generation). For `run_agent`:

- generated files usually come back as `files[].s3_key`
- there is no MCP tool today to download those bytes from the returned key
- large outputs may be trimmed by the MCP client

Backend file-response limits:

- only whitelisted output extensions are returned: `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, \
`.tiff`, `.pdf`, `.docx`, `.xlsx`, `.xls`, `.xlsm`, `.csv`, `.txt`, `.md`, `.json`, `.html`, \
`.xml`
- max size per file: 10 MB
- base64 mode is limited to 5 files, but `run_agent` uses `s3_key` responses

## Components And Availability

File/document behavior varies by component version and release stage.
Always call `list_components()` or `search_components()` in the active org before designing a \
file workflow.

Do not assume:

- a remembered component name is available
- an internal/beta file component is visible
- a component supports local paths, URLs, base64, or uploads unless the current catalog says so
"""

QA = """\
# QA & Evaluation

## Datasets

Test case collections for evaluating agent quality:

1. `list_datasets(project_id)` → find existing datasets
2. `create_dataset(project_id, dataset_data)` → create one or more datasets (`dataset_data.datasets_name`)
3. `update_dataset(project_id, dataset_id, dataset_name)` → rename a dataset
4. `delete_datasets(project_id, dataset_ids)` → batch delete

Dataset names are not unique — duplicates are allowed. Always call `list_datasets` first and \
reuse an existing `dataset_id` instead of creating a new dataset with the same name.

## Entries

Individual test cases within a dataset:

1. `list_entries(project_id, dataset_id)` → paginated response: \
`{pagination: {...}, inputs_groundtruths: [...]}`
2. `create_entries(project_id, dataset_id, inputs_groundtruths)` → batch create
3. `update_entries(project_id, dataset_id, inputs_groundtruths)` → batch update
4. `delete_entries(project_id, dataset_id, input_groundtruth_ids)` → batch delete
5. `save_trace_to_qa(project_id, dataset_id, trace_id)` → save a trace as a test case

Entry shape for create:

```json
{"input": {"role": "user", "content": "hello"}, "groundtruth": "expected answer"}
```

Optional fields: `position` (int >= 1), `custom_columns` (dict).

Entry shape for update (requires `id` from `list_entries`):

```json
{"id": "<entry-uuid>", "input": {"role": "user", "content": "updated"}, "groundtruth": "new answer"}
```

## Judges

LLM-based evaluators that score agent responses:

1. `list_judges(project_id)` → see judges
2. `get_judge_defaults` → default judge config template
3. `create_judge(project_id, judge_data)` → new judge
4. `update_judge(project_id, judge_id, judge_data)` → modify
5. `delete_judges(project_id, judge_ids)` → batch delete

Judge shape for create:

```json
{
  "name": "my-judge",
  "evaluation_type": "boolean",
  "prompt_template": "Return true if output equals expected, false otherwise.",
  "llm_model_reference": "openai:gpt-4o"
}
```

`evaluation_type` options: `boolean`, `score`, `free_text`, `json_equality`. \
Optional fields: `description` (str), `temperature` (float, default 1.0).

## Running Evaluations

1. `run_qa(project_id, dataset_id, config)` → run selected inputs or `run_all` against a `graph_runner_id`
2. `run_evaluation(project_id, judge_id, version_output_id)` → run one judge against a single version output
3. `get_evaluations(project_id, version_output_id)` → see results

Frontend/runtime habits to mirror:

- when a QA input changes, its existing `output`, `evaluations`, and `version_output_id` should be \
treated as stale
- bulk QA execution is run sequentially in the frontend to avoid server overload
- only evaluate rows that already have a valid `version_output_id`
"""

VERSIONING = """\
# Versioning

`graph_runner_id` is first-class context. Do not treat `project_id` alone as enough for graph edits, \
runs, or publish operations.

## True Editable Draft

The backend only allows graph edits on a runner that is:

- `env == "draft"`
- untagged (`tag_version` / `tag_name` is null)

A tagged snapshot is immutable even if it still feels like a draft-like version.

## Save Version vs Publish

### `save_graph_version(project_id, graph_runner_id)`

- creates an immutable tagged snapshot
- keeps the current draft runner as the editable draft
- does **not** remap current draft instance IDs

### `publish_to_production(project_id, graph_runner_id)`

- promotes the supplied runner to production
- creates a brand new draft runner for continued editing
- remaps instance UUIDs in that new draft

After publish, switch to the returned `draft_graph_runner_id` and call `get_graph` again before \
making more edits.

## Safe Workflow

1. `get_project_overview(project_id)` — identify the editable draft and current production runner
2. `get_graph(project_id, draft_runner_id)` — inspect current draft
3. `update_graph(...)` or `configure_agent(...)`
4. `save_graph_version(...)` — snapshot when ready
5. `publish_to_production(...)` — go live
6. switch to the returned new draft for further work

## Production-Only Surfaces

The frontend treats these flows as production-oriented:

- cron jobs / schedules
- endpoint polling / event triggers

If there is no production deployment yet, treat those capabilities as not live.
"""

PLAYGROUND = """\
# Playground And Runs

The frontend always operates against a selected runner. Mirror that habit in MCP: choose the \
appropriate `graph_runner_id` first, then run.

## Runner Selection

- For edits and iterative testing, use the editable draft runner.
- For live-behavior checks, production-oriented schedules, or public surfaces, reason from the \
production runner.
- If you are unsure, call `get_project_overview(project_id)` first.

## Agent vs Workflow Resolution

In the frontend, agents resolve `project_id` via the agent's backing project and workflows use the \
workflow project directly. In MCP you still provide both `project_id` and `graph_runner_id`, so the \
important rule is: do not mix runners from one project with another project ID.

## Execution Model

`run_agent(...)` starts async execution and polls until completion or timeout.

The frontend can also stream `202 Accepted` runs over websockets, but the current MCP wrapper only \
offers the polling-based abstraction.

## Conversation And Variables

Backend execution can use:

- `conversation_id` for multi-turn continuity
- `set_id` / `set_ids` for variable-set resolution

The current MCP wrapper does not expose those fields directly, so do not assume playground parity \
for those features.

## Traces And Replay

Use:

1. `list_runs(project_id)` / `get_run(project_id, run_id)`
2. `get_run_result(project_id, run_id)`
3. `list_traces(project_id)` / `get_trace_tree(trace_id)`

to inspect what happened after execution.
"""

INTEGRATIONS = """\
# Integrations And OAuth

## Component Selection

For agent tools, only `function_callable` components are valid.

If a component is not marked `function_callable` in the current catalog, do not attach it as an \
agent tool.

## OAuth Lifecycle

OAuth connections are not simple secret uploads. The real lifecycle is:

1. user authorizes in the web UI
2. backend confirms the connection
3. components and OAuth variable sets resolve against that connection

Current MCP surface (requires developer role):

- `list_oauth_connections(provider_config_key?)` — optional provider filter
- `check_oauth_status(provider_config_key, connection_id)` — check a specific connection
- `revoke_oauth(connection_id, provider_config_key)` — disconnect (destructive)

MCP does **not** expose the browser-based connect flow.

## Integration-Backed Components

Some components require an integration relationship in addition to normal parameters. Examples include \
OAuth-backed Gmail, Slack, or other provider-integrated tools.

Important MCP constraints:

- `add_tool_to_agent()` can create the tool entry but cannot create the required integration \
relationship automatically.
- **OAuth connections cannot be assigned via `update_graph`**. Passing an `oauth_connection_id` \
as a parameter value will be rejected by the backend. After creating the graph programmatically, \
the user must open the Draft'n Run web UI and manually select the OAuth connection on each \
OAuth-dependent component (Gmail, Slack, HubSpot, etc.).
- Use `list_oauth_connections` to verify which connections exist before telling the user what \
to connect in the UI.

If a component catalog entry includes an `integration` block, treat it as unsafe for the generic \
agent-tool helper unless the helper explicitly supports it.
"""

KNOWN_QUIRKS = """\
# Known Quirks

These are current backend/MCP behaviors the AI should actively work around.

## Graph Update Hash Excludes `port_mappings`

Current graph change detection hashes the graph while excluding `port_mappings`.

Consequence:

- a pure `port_mappings`-only edit can be treated as unchanged and skipped

Safest workaround:

- edit from the latest `get_graph(...)` payload
- prefer canonical edge wiring or field expressions when possible
- if you must rely on explicit `port_mappings`, validate carefully and be aware that save-time change \
detection is imperfect

## Relationship Deletion Path Is Not Explicit

`update_graph_service` clearly upserts provided relationships, but there is no explicit relationship \
deletion pass analogous to edge/node deletion in that service.

Consequence:

- structural relationship removals should be treated carefully and validated after saving

## Knowledge Chunk Replacement Is Source-Scoped

`update_document_chunks(...)` currently syncs vectors by `source_id`, not by `document_id`.

Consequence:

- omitted chunks can affect other vectors in the same source
- treat the tool as a risky full-replacement helper, not a routine partial-edit API

## Document Deletion Cleanup Is Incomplete

Logical document deletion removes DB rows by document/file ID, but vector cleanup is not guaranteed.

Consequence:

- use `delete_document(...)` only with explicit user confirmation

## `update_graph` Has No Dry-Run Mode

The entire graph must be submitted as one payload. Any single validation error (wrong port name, \
wrong UUID format, invalid parameter) fails the entire call with only the **first** error. There is \
no partial success and no dry-run mode.

Safest approach:

- always start from a `get_graph(...)` response and modify incrementally
- the MCP layer now warns about likely key typos (e.g. `ports_mappings` instead of `port_mappings`) \
before sending to the backend, but structural validation still happens server-side

## OAuth Connections Cannot Be Assigned Programmatically

`list_oauth_connections` returns valid connection IDs, but passing one as a parameter value in \
`update_graph` is rejected by the backend. OAuth connections must be assigned in the web UI.

See `docs://integrations` for details.

## Unknown Top-Level Keys In `update_graph` Are Silently Ignored

The backend accepts and ignores unknown keys in the graph payload. A common mistake is \
`ports_mappings` instead of `port_mappings` — the typo is accepted (200 OK) but the port \
mappings are silently dropped.

The MCP layer now warns about known typos, but less obvious unknown keys will still pass \
through silently.
"""

ADMIN = """\
# Administration

## API Keys

Project-level and org-level API keys for external integrations:

- `list_project_api_keys`, `create_project_api_key`, `revoke_project_api_key`
- `list_org_api_keys`, `create_org_api_key`, `revoke_org_api_key`

## Cron Jobs

Scheduled agent execution:

1. `list_crons()` → see organization cron jobs
2. `create_cron(cron_data)` → new schedule (see tool docstring for payload shape)
3. `update_cron(cron_id, cron_data)` → modify
4. `delete_cron(cron_id)` → remove
5. `pause_cron(cron_id)` / `resume_cron(cron_id)` → toggle without deleting
6. `get_cron_runs(cron_id)` → execution history

Important runtime notes:

- cron write operations (create, update, delete, pause, resume) require developer role
- cron jobs are organization-scoped in MCP
- the frontend treats schedules as production-oriented behavior
- successful CRUD writes DB state first; scheduler pickup can lag slightly

Cron expression format:

- standard five-field crontab: `minute hour day-of-month month day-of-week`
- use textual weekday names for day-of-week ranges — `mon-fri`, not `1-5`
- example: `0 9 * * mon-fri` (preferred) vs `0 9 * * 1-5` (avoid)
- textual names are unambiguous across cron implementations and easier to read at a glance

## OAuth Connections

OAuth integrations (Slack, Gmail, HubSpot) must be set up in the web UI. Requires developer role.

- `list_oauth_connections(provider_config_key?)` → list connections, optional provider filter
- `check_oauth_status(provider_config_key, connection_id)` → check a specific connection's status
- `revoke_oauth(connection_id, provider_config_key)` → disconnect (destructive — confirm first)

Always ask the user before guiding OAuth setup or revoking an existing connection. MCP exposes \
read/revoke operations only; the actual connect flow happens in the web UI.

## Monitoring

- `list_traces(project_id)` → recent traces
- `get_trace_tree(trace_id)` → full span tree with timings
- `get_org_charts(duration_days)` → usage charts (1–365 days)
- `get_org_kpis(duration_days)` → key metrics
- `get_credit_usage` → credit consumption
"""

DOMAINS: dict[str, str] = {
    "getting-started": GETTING_STARTED,
    "agent-config": AGENT_CONFIG,
    "graphs": GRAPHS,
    "versioning": VERSIONING,
    "components": COMPONENTS,
    "execution": EXECUTION,
    "playground": PLAYGROUND,
    "variables": VARIABLES,
    "knowledge": KNOWLEDGE,
    "file-management": FILE_MANAGEMENT,
    "integrations": INTEGRATIONS,
    "known-quirks": KNOWN_QUIRKS,
    "qa": QA,
    "admin": ADMIN,
}

DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "getting-started": "First steps, RBAC, role hierarchy, constraints",
    "agent-config": "Configure agents: model, tools, system prompt",
    "graphs": "Graph structure, edges, port mappings, field expressions",
    "versioning": "Draft vs production, graph runners, save vs publish",
    "components": "Component catalog, parameter/port types",
    "execution": "Running agents, payloads, inspecting runs",
    "playground": "Runner selection, sync vs async runs, traces, execution habits",
    "variables": "Variable definitions, sets, secrets, resolution",
    "knowledge": "Knowledge base sources & documents",
    "file-management": "Knowledge documents, file inputs/outputs, and current limits",
    "integrations": "Function-callable tools, OAuth lifecycle, integration-backed components",
    "known-quirks": "Backend/MCP caveats that require explicit workarounds",
    "qa": "QA datasets, judges, evaluations",
    "admin": "API keys, crons, OAuth, monitoring",
}


def _make_resource_fn(content: str):
    """Create a named function returning static content (FastMCP rejects lambdas)."""
    def resource_fn() -> str:
        return content
    return resource_fn


def register(mcp: FastMCP) -> None:
    missing = DOMAINS.keys() - DOMAIN_DESCRIPTIONS.keys()
    extra = DOMAIN_DESCRIPTIONS.keys() - DOMAINS.keys()
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"DOMAIN_DESCRIPTIONS missing keys: {sorted(missing)}")
        if extra:
            parts.append(f"DOMAINS missing keys: {sorted(extra)}")
        raise ValueError(f"DOMAINS / DOMAIN_DESCRIPTIONS mismatch — {'; '.join(parts)}")

    for domain, content in DOMAINS.items():
        description = DOMAIN_DESCRIPTIONS[domain]
        fn = _make_resource_fn(content)
        fn.__name__ = domain.replace("-", "_")
        mcp.resource(f"docs://{domain}", name=domain, description=description)(fn)

    @mcp.tool()
    async def get_guide(domain: str) -> str:
        """Fetch detailed documentation for a domain.

        Available domains: getting-started, agent-config, graphs, versioning,
        components, execution, playground, variables, knowledge,
        file-management, integrations, known-quirks, qa, admin.
        """
        if domain not in DOMAINS:
            available = ", ".join(sorted(DOMAINS.keys()))
            raise ValueError(f"Unknown domain '{domain}'. Available: {available}")
        return DOMAINS[domain]
