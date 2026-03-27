# Draft'n Run MCP Server

Standalone [MCP](https://modelcontextprotocol.io/) server that wraps the Draft'n Run backend API and Supabase direct queries behind an authenticated, tool-based interface. Connects to Cursor, Claude Desktop, or any MCP-compatible client via Streamable HTTP at `https://mcp.draftnrun.com`.

## Architecture

```text
MCP Client (Cursor / Claude)
    │
    │ Streamable HTTP + Bearer {supabase_jwt}
    ▼
┌──────────────────────────┐
│   MCP Server (this pod)  │
│   FastMCP + Sentry       │
│   Port 8090              │
├──────────────────────────┤
│  ┌─────────┐ ┌────────┐ │
│  │ Backend │ │Supabase│ │     Redis
│  │ Client  │ │ Client │ │◄───(org session)
│  └────┬────┘ └───┬────┘ │
└───────┼──────────┼───────┘
        │          │
        ▼          ▼
   ada-api:8000  Supabase
   (projects,    (orgs, members,
    graphs,       invites, auth,
    runs, etc.)   release stages)
```

- **Auth**: Supabase OAuth 2.1 Server via FastMCP's `SupabaseProvider` — no custom tokens.
- **RBAC**: User role (from org membership) is cached in Redis and enforced on sensitive tools. Variables/secrets require admin; deletions require developer+.
- **Release Stage**: Org's release stage is fetched on `select_organization` and auto-applied to component catalog queries. The AI cannot escalate beyond the org's tier.
- **Org context**: Session-scoped in Redis (24h TTL), keyed by the MCP session when the client provides one. Call `select_organization` before using org-scoped tools.

## Prerequisites

1. **Supabase OAuth Server** enabled in dashboard (Authentication → OAuth Server)
2. **Consent page** deployed in `back-office/` at `/oauth/callback`
3. Environment variables (see below)

## Environment Variables

| Variable | Example | Required |
|---|---|---|
| `SUPABASE_PROJECT_URL` | `https://xyz.supabase.co` | Yes |
| `SUPABASE_PROJECT_KEY` | `eyJ...` (anon key) | Yes |
| `MCP_BASE_URL` | `http://localhost:8090` | No |
| `BACKEND_URL` | `http://ada-api` | Yes |
| `REDIS_URL` | `redis://:password@redis:6379` | Yes |
| `SENTRY_DSN` | `https://...@sentry.io/...` | No |
| `SENTRY_ENVIRONMENT` | `production` | No |

## Progressive Disclosure (docs:// resources)

Documentation is split into domain-specific MCP resources. The AI gets a compact domain index in the server `instructions` and fetches only the domain it needs. A `get_guide(domain)` tool provides the same content for clients that don't support resources.

| Resource | Domain |
|---|---|
| `docs://getting-started` | First steps, RBAC, role hierarchy, constraints |
| `docs://agent-config` | Configure agents: model, tools, system prompt |
| `docs://graphs` | Graph structure, edges, port mappings, field expressions |
| `docs://versioning` | Draft vs production, graph runners, save vs publish |
| `docs://components` | Component catalog, parameter/port types |
| `docs://execution` | Running agents, payloads, inspecting runs |
| `docs://playground` | Runner selection, async runs, traces, execution habits |
| `docs://variables` | Variable definitions, sets, secrets, resolution |
| `docs://knowledge` | Knowledge base sources & documents |
| `docs://file-management` | Knowledge documents, file inputs/outputs, and current limits |
| `docs://integrations` | Function-callable tools, OAuth lifecycle, integration-backed components |
| `docs://known-quirks` | Backend/MCP caveats that require explicit workarounds |
| `docs://qa` | QA datasets, judges, evaluations |
| `docs://admin` | API keys, crons, OAuth, monitoring |

All domain content lives in `docs.py` (single source of truth).

## Tool Reference

~90 tools across 14 modules. Use `get_guide(domain)` or the docs:// resources above for detailed usage.

| Module | Tools | Highlights |
|---|---|---|
| Context | 5 | `list_my_organizations`, `select_organization`, `get_current_context` |
| Projects | 7 | `create_workflow` (auto ID/icon), `get_project_overview` |
| Agents | 3 | `create_agent` (auto ID/icon — single AI node; use `create_workflow` for DAGs) |
| Agent Config | 3 | `configure_agent`, `add_tool_to_agent`, `remove_tool_from_agent` |
| Graphs | 8 | `get_graph`, `get_draft_graph` (auto-resolves draft runner), `update_graph`, `update_component_parameters`, `save_graph_version`, `publish_to_production`, `promote_version_to_env`, `get_graph_history` |
| Components | 2 | `list_components` (auto-filtered by release stage), `search_components` |
| Runs | 4 | `run` (payload dict, async + polling), `list_runs`, `get_run`, `get_run_result` |
| API Keys | 6 | Project + org level keys |
| Variables | 9 | Admin only — definitions, sets, secrets |
| Knowledge | 9 | `create_source` (website/database), sources, documents, chunks |
| QA | 20 | Datasets, entries, custom columns, CSV export/import, judges, evaluations |
| Monitoring | 5 | Traces, charts, KPIs, credits |
| Crons | 9 | Create, pause/resume, manual trigger, execution history |
| OAuth | 3 | List, check status, revoke |
| **Docs** | **1** | **`get_guide(domain)` — fallback for domain docs** |

`get_project_overview(project_id)` is the default orientation tool for any version-aware work. It now returns the editable draft runner, current production runner, production-only capability hints, warnings, and safe next steps.

### Proxy-tool factory (`tools/_factory.py`)

Most tools are single-call API proxies. Instead of hand-writing the auth/org/role + API call boilerplate for each, they are declared as `ToolSpec` data and registered via `register_proxy_tools()`:

```python
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

SPECS = [
    ToolSpec(
        name="list_crons",
        description="List all cron jobs in the active organization.",
        method="get",
        path="/organizations/{org_id}/crons",
        scope="org",
        return_annotation=dict,
    ),
]

def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
```

ToolSpec also supports `trim=False` to disable response truncation on specific tools (e.g. `get_graph` for round-trip safety). Specs are validated at registration time — unresolved path placeholders, invalid body_org_key, and missing roles cause immediate errors.

Custom tools (validation, multi-step, client-side logic) are still defined as `@mcp.tool()` functions alongside factory specs in the same module. See `_factory.py` docstring and cursor rule `20-mcp-server.mdc` for details.

## Guardrails

| Guard | Description |
|---|---|
| RBAC | Variables/secrets require admin. Deletions require developer+. `create_agent`, cron writes (create/update/delete/pause/resume), OAuth tools, and `update_document_chunks` require developer+. `trigger_cron` requires member role or above. `invite_org_member` checks admin/super_admin on the target org, not just the active org. |
| Component search | `search_components` rejects blank or whitespace-only queries. |
| Release stage | Component catalog auto-filtered by org tier. Cannot be overridden by the AI. |
| Agent name | `create_agent` rejects empty/whitespace names. |
| Pagination | `list_runs` caps page_size at 100. |
| Monitoring | Duration clamped 1–365 days. |
| Response size | Responses > 50KB are trimmed by default. `ToolSpec.trim=False` disables trimming per tool (e.g. `get_graph`, `list_components` for round-trip safety). |
| Session diagnostics | `get_current_context` includes `session.session_id` and `session.storage_backend` ("redis" or "memory"). |
| Agent tools | `add_tool_to_agent` rejects non-`function_callable`, duplicate, or integration-backed tools that it cannot wire safely. Use the display name from `search_components()`, not hard-coded names. |
| Model validation | `configure_agent` validates the requested model against the agent's available options and rejects unknown or deprecated names with a clear error listing valid choices. |
| Source creation | `create_source` validates type-specific required fields and only supports `website`/`database` (developer+ role). |
| Knowledge mutation | `update_document_chunks` is blocked by default unless the caller explicitly confirms a full replacement. |
| Graph null IDs | `update_graph` auto-generates UUIDs for component instances **and edges** with `id: null`. |
| Canonical field expressions | The backend auto-generates a visible, editable RefNode field expression (e.g. `@{{<source_uuid>.output}}`) for canonical inputs when an edge exists and no user expression is set. User-provided expressions are never overwritten. The MCP should create edges and let the backend handle canonical wiring. |
| Tool port configurations | Tool input ports support three setup modes: `ai_filled` (default, AI provides value), `user_set` (pre-configured, hidden from AI), `deactivated` (removed from tool interface). Managed via `port_configurations` in `get_graph`/`update_graph`. |
| Unknown graph keys | `update_graph` warns about unrecognised top-level keys (e.g. `ports_mappings` → `port_mappings`) before forwarding. |
| Graph guide warning | `update_graph` tool description warns callers to `get_guide('graphs')` first and to close the browser tab before API edits. |
| Optimistic locking | `update_graph` accepts optional `last_edited_time` for conflict detection (409 Conflict if the graph was modified since that timestamp). |
| Edge format coercion | Edge `origin`/`destination` accept both plain UUID strings and dicts like `{"instance_id": "uuid"}` — the backend normalizes. |
| JSON param coercion | JSON-typed parameters (e.g. If/Else `conditions`) accept native lists — the backend serializes them automatically. |
| Error detail | 403 and 404 backend errors now include the backend's error detail instead of generic messages. |
| Docs sync | Any MCP behavior change must update `docs.py` resources and this README together. |

## AI Builder Habits

- Never copy IDs, instance UUIDs, source IDs, or graph JSON from another project/org as a shortcut. Always inspect the current org/project first with `get_graph`, `list_components`, `search_components`, and the relevant `list_*` tools.
- **Never hard-code model names** — models are deprecated regularly. Discover valid models from the agent's `completion_model` parameter options via `get_graph()`, then pass the exact `value` to `configure_agent()`.
- **Never hard-code component names** — discover them with `search_components()` and pass the exact display name to `add_tool_to_agent()`.
- Ask clarifying questions before making architecture decisions that affect edge cases, retries, file lifecycle, routing, or user-visible behavior.
- Ask for explicit user permission before destructive or external-account actions such as publish, delete, revoke OAuth, or guiding OAuth connection setup in the web UI.
- Prefer dedicated components over generic code. Use search, RAG, integration, file, and document components when available. Keep `python_code_runner` and `terminal_command_runner` for small, bounded transformations or glue work.
- Treat `_truncated: true` responses as incomplete data. Missing graph fields, file outputs, or document content must be treated as unknown.

## File And Document Guardrails

- Fetch `docs://file-management` before mutating knowledge documents or building file-centric workflows.
- Knowledge documents are logical groups of ingested chunks, not a general binary file store and not guaranteed to be downloadable originals.
- MCP does not currently expose an end-to-end file upload/download workflow. The `run` tool accepts a `payload` dict (containing `messages` and optional custom Start fields), and generated files usually come back as `files[].s3_key`.
- `create_source` supports `website` and `database` types. For `local` (file upload) and `google_drive` (OAuth), use the web product.
- `update_source` re-triggers ingestion with the stored source definition. It does NOT accept config changes — `source_data` is ignored.
- `update_document_chunks` and `delete_document` are sharp tools. Only use them with explicit user confirmation and a fully understood desired end state.

## Local Development

```bash
uv sync --group mcp-server

export SUPABASE_PROJECT_URL=http://localhost:54321
export SUPABASE_PROJECT_KEY=your-anon-key
export MCP_BASE_URL=http://localhost:8090
export BACKEND_URL=http://localhost:8000
export REDIS_URL=redis://:redis_password@localhost:6379

uv run python -m mcp_server.server
```

Test with [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector http://localhost:8090/mcp
```

## Deployment

The MCP server runs as a standalone Kubernetes pod (`ada-mcp`) alongside the API. The `build-and-deploy-k8s.yml` workflow builds the Docker image, pushes it to GHCR, and rolls out the deployment in the same pipeline as the other services. MCP rollout failure is non-blocking — it will not fail the overall deploy.

- **Dockerfile**: `mcp_server/Dockerfile`
- **Image**: `ghcr.io/scopeo/draftnrun-mcp-server`
- **K8s manifests**: `infra/k8s/base/mcp-*.yaml`
- **Ingress**: `mcp-staging.draftnrun.com` / `mcp.draftnrun.com`

## Auth Flow

1. MCP client connects without a token → server returns 401 + Supabase AS discovery metadata
2. Client performs OAuth 2.1 PKCE flow with Supabase
3. User logs in at Supabase, gets redirected to `https://app.draftnrun.com/oauth/callback`
4. User approves → Supabase issues tokens
5. Client sends tool calls with `Bearer {supabase_jwt}` → MCP server validates via Supabase JWKS
6. Same JWT is forwarded to the Draft'n Run backend

The consent page lives in `back-office/src/pages/oauth/callback.vue`.

## Client Configuration

### Cursor

Add to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "draftnrun": {
      "url": "https://mcp.draftnrun.com/mcp"
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`):

```json
{
  "mcpServers": {
    "draftnrun": {
      "type": "http",
      "url": "https://mcp.draftnrun.com/mcp"
    }
  }
}
```

> **Note**: Claude Desktop requires the explicit `"type": "http"` field. Without it, the connection will fail.

### Other MCP Clients

Any Streamable-HTTP-compatible MCP client can connect to `https://mcp.draftnrun.com/mcp`. Authentication is handled automatically via the OAuth 2.1 flow described above. If your client asks for a transport type, select **HTTP** (not SSE, not stdio).

## Troubleshooting

**"Not authenticated" / no tools visible** — The MCP client hasn't completed the OAuth flow. Check your client's MCP server status and reconnect. After auth, call `get_current_context()` to verify your session.

**"No organization selected"** — Call `list_my_organizations` then `select_organization` **sequentially** (not in parallel). All org-scoped tools fail until an org is selected. Parallel calls with `select_organization` will race and fail. Use `get_current_context()` to verify session state.

**"This operation requires one of ('admin', 'super_admin') role"** — Your org role doesn't allow this operation. Check with `get_current_context()`.

**401 on tool calls** — Token expired. The MCP client should handle token refresh via Supabase. Reconnect if refresh fails.

**Tools returning 403** — Your role in the organization may not have sufficient permissions, or the org's release stage may not include the requested resource. Check with `get_current_context`. The error message now includes the backend's detail when available.

**"access_token is required" on `update_graph`** — The graph contains an integration-backed component (e.g. Gmail, Slack, HubSpot) whose OAuth connection is not set up. The backend validates integration dependencies at save time, not just at run time. Fix: connect the integration in the web UI first, or save the graph without the integration component and add it later. See `docs://integrations` preflight checklist.

**"Resource not found" on graph/project operations** — IDs may have changed after a publish (which creates a fresh draft with new instance UUIDs). Re-fetch with `get_project_overview` and `get_graph` before retrying. Never reuse IDs across projects or orgs.

**UUID parse errors (e.g. "invalid group count")** — A malformed UUID was passed (wrong hyphen placement or missing group). Double-check the ID has the format `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (5 hyphen-separated groups). Copy IDs verbatim from tool responses. To avoid `graph_runner_id` errors entirely, use `get_draft_graph(project_id)` which resolves the draft runner automatically.

**`list_projects` returns projects from other organizations** — When `include_templates=True`, the backend includes global template projects from all orgs. Filter the response by `organization_id` to isolate the active org's projects, or use `include_templates=False` (the default).
