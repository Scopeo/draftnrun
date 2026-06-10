# Graph Execution Engine

The engine executes workflow graphs (DAGs) of components. Each component is a typed processing unit with Pydantic I/O schemas, connected via field expressions.

## GraphRunner

**File**: `engine/graph_runner/graph_runner.py`

The `GraphRunner` takes a `networkx.DiGraph`, a dict of `Runnable` instances keyed by instance ID, and optional expressions and variables.

### Initialization

1. Adds a virtual `__input__` node with edges to all start nodes
2. Builds `_expressions_by_node` index: per-target-node list of `(field_name, expression_ast)` from raw expression dicts
3. Augments graph edges from expression ref dependencies (`_augment_graph_with_dependencies`)
4. Validates the graph is acyclic and all expressions are valid

### Execution Loop (`_run_without_io_trace`)

1. **Initialize**: Create `Task` objects for every node with `pending_deps = in_degree(node)`. Complete the virtual `__input__` with initial data.
2. **Main loop**: Find next `READY` task (pending_deps == 0)
3. For each ready node:
   - `_gather_inputs()` — assemble input dict from field expressions; start nodes with no real predecessors are seeded with the initial input data
   - Wrap into `NodeData(data=..., ctx=run_context)`
   - Call `runnable.run(input_packet)`
   - Normalize output to `NodeData`
   - Merge output `ctx` back into shared `run_context`
4. **Handle directive** from result:
   - `CONTINUE` — decrement all successors' pending deps
   - `HALT` — BFS-mark downstream (and branch roots skipped by selective routing) as `HALTED` with empty `NodeData` (nodes already `COMPLETED`, e.g. the halting node, are left unchanged)
   - `SELECTIVE_EDGE_INDICES` — only specific successors proceed based on edge `order` attribute
5. **Collect outputs**: Gather leaf node results into final response

### Task States

```text
NOT_READY → READY (pending_deps reaches 0) → COMPLETED (after execution)
NOT_READY → HALTED (branch skipped; empty NodeData; excluded from legacy leaf output collection)
```

## Component Protocol

**Files**: `engine/graph_runner/runnable.py`, `engine/components/component.py`

### Runnable Protocol

```python
class Runnable(Protocol):
    tool_description: ToolDescription
    async def run(self, *inputs) -> AgentPayload | NodeData
    def get_canonical_ports(cls) -> Dict[str, Optional[str]]
    def get_inputs_schema(cls) -> Type[BaseModel]
    def get_outputs_schema(cls) -> Type[BaseModel]
```

### Component ABC

The concrete base class implementing `Runnable`. Key attributes:
- `migrated: bool = False` — distinguishes new (typed I/O) vs legacy components

**`run()` dispatches based on migration status:**
- **Migrated**: validates inputs against `get_inputs_schema()`, calls `_run_without_io_trace(inputs, ctx)`, validates output, extracts `ExecutionDirective`
- **Unmigrated**: converts `NodeData` to legacy `AgentPayload`, calls `_run_without_io_trace()`, converts back

**`_run_without_io_trace(inputs: BaseModel, ctx: dict) -> BaseModel`** is the abstract method subclasses implement.

### Python Code Runner Artifacts

`PythonCodeRunner` preserves the full E2B execution payload at `artifacts.execution_result`. When the execution returns a
text result, it also exposes that value as `artifacts.text` so downstream field expressions can inject it with
`@{{<python_runner_instance_id>.artifacts::text}}` without relying on nested array traversal.

When a tracing context provides `shared_sandbox`, the runner reuses it only after a successful async health check on the
current event loop. If the health check fails, including closed-loop errors from a previously cached E2B client, the helper
discards the stale sandbox and creates a fresh one for the current context.

### Component Catalog Lifecycle

When removing a component from the product, delete the runtime class, registry entry, seed data, existing DB catalog rows (with a migration), default tool description, and wrapper components that only exist to call it. Leaving only part of the catalog wiring in place can keep a dead component instantiable through backend seeds or MCP graph validation even after it disappears from the front-end.

Integration-backed catalog entries can share a runtime class while using distinct OAuth provider keys. For example, Gmail Neverdrop reuses `GmailSenderV2` with `google-mail-neverdrop`, Google Calendar Neverdrop reuses `GoogleCalendarMCPTool` with `google-calendar-neverdrop`, and Google Contacts Neverdrop uses the read-only `GoogleContactsMCPTool` with `google-contact-neverdrop`. Gmail Neverdrop must remain send-only: drafts are disabled, recipients are required, and no `save_as_draft` runtime argument is exposed. Neverdrop-branded Google integration tools should remain agent-available (`is_agent=True`) and function-callable. Google Contacts Neverdrop lists both regular contacts and Google Other contacts by default, using separate People API pagination tokens and an Other contacts `readMask` that excludes unsupported regular-contact fields such as `organizations`. List calls always pass `requestSyncToken=True` and return `nextSyncToken` / `nextOtherContactsSyncToken` on the last page; callers can pass `sync_token` / `other_contacts_sync_token` for incremental change feeds (deleted people arrive with `metadata.deleted`, and an expired token surfaces Google's `EXPIRED_SYNC_TOKEN` error — fall back to a full list). `contacts_search_contacts` searches both sources via `people.searchContacts` and `otherContacts.search` (capped at 30 results per source, with an empty first result treated as the cache warmup — wait ~2s and retry once — and an Other contacts search `readMask` limited to names/emails/phones/metadata). Its OAuth provider config must include both `contacts.readonly` and `contacts.other.readonly` scopes. Google API discovery services used from async MCP clients should be built inside each `asyncio.to_thread` call because the google-api-python-client service/HTTP stack is not thread-safe across worker threads.

HubSpot MCP `notes_upsert_for_contact` accepts `properties.hs_timestamp` as optional. When omitted or empty, the tool sends the current UTC timestamp to HubSpot in ISO-8601 `Z` format before creating or updating the note.

Unified Mail Sender versions must keep their seed-time Gmail provider and registry OAuth binding in sync. For example, `mail_sender_v2` exposes a Gmail Neverdrop connection in the catalog, so its `gmail_oauth_connection_id` registry binding resolves with `OAuthProvider.GMAIL_NEVERDROP`; older unified Mail Sender versions that expose regular Gmail continue resolving with `OAuthProvider.GMAIL`. The standalone Gmail Neverdrop catalog entry remains send-only, but unified `mail_sender_v2` exposes `save_as_draft` for Gmail or Outlook sends and defaults it to `true`.

Mail sender components (`Gmail Sender`, `Gmail Neverdrop`, `Outlook Sender`, and unified `Mail Sender`) accept `email_attachments` as legacy string path/URL entries or provider-safe object entries shaped like `{"url": "...", "filename": "..."}` or `{"path": "...", "filename": "..."}`. String attachments are normalized to object attachments before runtime. Object attachments download from `url` or read from `path` and attach using the provided `filename`, which lets workflows control the displayed file name in Gmail MIME messages and Microsoft Graph payloads. Attachment URL downloads validate each URL and redirect target before streaming, rejecting non-HTTP(S) schemes and private/reserved network addresses. HTTPS downloads connect to the validated resolved IP while preserving the original hostname for SNI and certificate verification.

When changing the public attachment input contract, seed a new `ToolDescription` row and point only the new component version at it. Older mail sender component versions keep legacy string-item tool descriptions while the runtime remains backwards-compatible.

### Component Instantiation DB Usage

`ada_backend/services/agent_builder_service.py` instantiates graph components while holding the graph-building SQLAlchemy
session. Any database lookups needed to prepare factory inputs should use that existing session before calling
`FACTORY_REGISTRY.create(...)`. Factory parameter processors in `ada_backend/services/entity_factory.py` should consume
already-resolved values and avoid opening their own `get_db_session()` for per-component metadata such as LLM model IDs,
because nested checkouts multiply connection-pool pressure during concurrent runs.

### LLM Service Defaults

Engine completion, web search, and vision service constructors use OpenAI by default. The default chat-capable model for completion, web search, and
vision services is `gpt-5-mini` (`openai:gpt-5-mini` when represented as a provider-qualified model reference). The
component catalog's default `completion_model` parameter also uses `openai:gpt-5-mini`.

Google/Gemini function-calling uses an OpenAI-compatible endpoint, but replayed Gemini function-call parts require hidden
`thought_signature` data that the endpoint response does not expose. `GoogleProvider` therefore normalizes multi-turn
tool history by omitting prior assistant `tool_calls` and passing each `tool` response back as user-visible tool-result
context.

## Port System

Three layers spanning database (backend) and runtime (engine):

### Layer 1: PortDefinition (catalogue)

**Table**: `port_definitions` — static I/O schema per component version.

Key fields: `name`, `port_type` (INPUT/OUTPUT), `is_canonical`, `parameter_type`, `ui_component`, `drives_output_schema`.

### Layer 2: PortInstance (per graph instance)

Uses joined-table polymorphism:
- **`InputPortInstance`**: adds `field_expression_id` FK — links a configured value (FieldExpression) to an input port
- **`OutputPortInstance`**: materializes dynamic output ports (e.g. from `drives_output_schema`)

### Layer 3: FieldExpression (wiring and transforms)

**Table**: `field_expressions` — JSONB AST stored in `expression_json`. This is the sole wiring mechanism between components; there is no separate port_mappings table.

See [payload-and-data-flow.md](payload-and-data-flow.md) for the AST format.

## ExecutionDirective

**File**: `engine/components/types.py`

Controls post-node execution flow:

| Strategy | Behavior |
|---|---|
| `CONTINUE` | Default — all successors execute |
| `HALT` | Successors of the halting node (already `COMPLETED`) are marked `HALTED` with empty data |
| `SELECTIVE_EDGE_INDICES` | Only edges matching listed `order` indices proceed; non-selected successors and their subgraphs marked `HALTED` |

Used by: Router (selective routing), If/Else (true/else routing).

If/Else uses fixed edge orders: `0` for the true branch and `1` for the false/else branch. The false route is controlled by the `enable_false_path` component parameter, which defaults to `false`. When disabled, a false condition selects no branch and all successors are halted; when enabled, a false condition selects the `order=1` branch.

## Variable Resolution

**File**: `ada_backend/services/variable_resolution_service.py`

Merge order: **defaults → set_ids[0] → set_ids[1] → ...**

1. Load all `VariableDefinition` rows for the org
2. Apply defaults (secret type → secret row with `set_id=None`; other → `definition.default_value`)
3. Layer variable sets in order, each overriding previous values
4. Secret values are returned as `SecretStr` objects from `pydantic` (masked by `str()`/`repr()`)
5. Returns `dict[str, Any]` consumed by `VarNode` expression evaluation

Keep values as `SecretStr` through resolution/evaluation. Unwrap only at explicit execution boundaries that require
plaintext (for example prompt rendering or external client construction). The trace serializer
(`engine/trace/serializer.py`) masks `SecretStr` values before span export.

### Secret Redaction

Primary boundary: typed `SecretStr` + explicit unwrap at boundaries.
`shared/log_redaction.py` (`redact_sensitive`, `scrub_sentry_event`) is best-effort defense-in-depth for
untyped inputs/events where `SecretStr` cannot be applied directly. It lives in a runtime-neutral shared package so
API, scheduler, engine, and Redis worker processes can all reuse the same scrubbing logic without crossing package
boundaries.

## Legacy Compatibility

**File**: `engine/legacy_compatibility.py` (marked for deletion after migration)

Bridges unmigrated components (using `AgentPayload` in/out) with the new multi-port `NodeData` system. Key indicators:
- `Component.migrated = False` — checked in `run()` and `_validate_expressions()`
- Unmigrated components don't use coercion and receive the entire `task_result.data` dict

## SQL Local Storage Lifecycle

`SQLLocalService` caches SQLAlchemy engines by `engine_url` at process level instead of creating one pool per
instantiation. This prevents connection-pool growth when services are repeatedly created for the same database URL
(notably ingestion DB flows).
In ingestion flows, prefer reusing an existing `SQLLocalService` instance inside the same job and always call
`await close()` in `finally` blocks to release ref-counted engine ownership.
In ingestion workers, `ingestion_script.ingest_db_source.upload_db_source()` should create one source
`SQLLocalService` per ingestion run and reuse it across the run before closing it in `finally`.

## Tracing Context to Sentry Tags

**File**: `engine/trace/span_context.py`

`set_tracing_span(**kwargs)` is the canonical way to update tracing context and sync searchable fields to Sentry.
`reset_tracing_span()` clears context at top-level boundaries between independent runs.

- Keep searchable field mapping in `SENTRY_TAG_FIELDS`.
- Avoid mutating `TracingSpanParams` directly; use helper functions.
- `SENTRY_TAG_FIELDS` maps `TracingSpanParams` attributes to Sentry keys (e.g., `environment` -> `env`).
- Sync handles `None` by clearing tags/attributes to avoid stale values.
- `run_id` is injected at run boundaries (`run_with_tracking`, async enqueue, worker processing).
- Avoid mutating `TracingSpanParams` directly; always use the helper functions.
- `SENTRY_TAG_FIELDS` defines the allowlist propagated to Sentry (`cron_id`, `trace_id`, `project_id`,
  `organization_id`, `environment`, `call_type`, `graph_runner_id`, `tag_name`)
- non-`None` values are converted to strings and sent via `sentry_sdk.set_tag`
- `None` values remove the tag from the current Sentry isolation scope (`remove_tag`) to avoid stale tag leakage
- calling `set_tracing_span` is safe when Sentry is disabled; tag operations are no-ops until `sentry_sdk.init` runs

When introducing a new tracing field, add it to `TracingSpanParams` first. If it should be searchable in Sentry,
also add it to `SENTRY_TAG_FIELDS` so the propagation remains centralized and endpoint-agnostic.
## Ingestion Presigned URL Mode

Folder-source ingestion can optionally force presigned URL usage for S3-backed files via
`IS_CLOUD_S3` in environment settings:

- `IS_CLOUD_S3 = False` (default): ingestion never requests presigned URLs and always reads file content directly.
  `S3FolderManager.get_file_presigned_url()` returns `None` in this mode and does not attempt URL generation.
  Use this for local/dev and custom `S3_ENDPOINT_URL` setups (for example MinIO/LocalStack).
- `IS_CLOUD_S3 = True`: ingestion passes a presigned URL getter into document chunking for supported parsers.
  This mode is intended for cloud AWS S3 deployments where generated presigned URLs are externally reachable.
- When enabled, missing S3 metadata (`s3_path`), custom endpoint configuration (`S3_ENDPOINT_URL`), or presigned URL
  generation failures are treated as hard errors instead of silently falling back.

## Field Expression Parsing

`parse_expression_flexible()` accepts strings, serialized AST dicts, and plain JSON dicts/lists. Plain JSON dicts/lists
become `LiteralNode(json.dumps(value))`. Booleans that configure component behavior should be modeled as component
parameters rather than field expressions.

## Key Files

| Concept | File |
|---|---|
| GraphRunner | `engine/graph_runner/graph_runner.py` |
| Runnable Protocol | `engine/graph_runner/runnable.py` |
| Component ABC | `engine/components/component.py` |
| Task (engine) | `engine/graph_runner/types.py` |
| NodeData / ExecutionDirective | `engine/components/types.py` |
| Port management | `engine/graph_runner/port_management.py` |
| Field expression AST | `engine/field_expressions/ast.py` |
| Expression evaluation | `engine/graph_runner/field_expression_management.py` |
| Coercion matrix | `engine/coercion_matrix.py` |
| Legacy compatibility | `engine/legacy_compatibility.py` |
| Variable resolution | `ada_backend/services/variable_resolution_service.py` |
| DB models (ports) | `ada_backend/database/models.py` — search for `PortDefinition`, `PortInstance` |
| OTel span → SQL (`traces` DB) | `engine/trace/sql_exporter.py` — `SQLSpanExporter` parses each span once and passes the JSON dict into export |
| Qdrant service | `engine/qdrant_service.py` |

## Hybrid Search

The Retriever component supports three search modes via the `search_mode` parameter (`SearchMode` enum in `engine/qdrant_service.py`):

- **`semantic`** (default) — Dense vector search only (OpenAI embeddings). Uses `/points/query` with `using="dense"`.
- **`keyword`** — Sparse BM25 word-based search only. Uses Qdrant's server-side BM25 inference (`model: "Qdrant/bm25"`).
- **`hybrid`** — Combines dense + sparse search with Reciprocal Rank Fusion (RRF). Uses the `/points/query` endpoint with two `prefetch` sub-queries fused via `{"fusion": "rrf"}`.

All collections are hybrid: named dense vector `"dense"` + sparse vector `"sparse"` (IDF modifier). Existing dense-only collections are migrated via Alembic revision `b2c3d4e5f6a0`.

### Versioning

Existing component versions (RAG v3 `0.2.0`, Retriever `0.0.1`, Retriever Tool `0.0.1`) do not expose `search_mode` — they default to `semantic` for backward compatibility. New versions (RAG v4 `0.3.0` in `seed_rag_v4.py`, Retriever v2 `0.0.2`, Retriever Tool v2 `0.0.2`) add `search_mode` as a user-configurable parameter (default `semantic`).

### Ingestion

Each upserted point carries both a dense embedding and a BM25 document inference object:

```json
{
    "vector": {
        "dense": [0.1, 0.2, ...],
        "sparse": {"text": "chunk content", "model": "Qdrant/bm25"}
    }
}
```
