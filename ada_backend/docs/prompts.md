# Org-Level Prompt Library

## Overview

Prompts are first-class, org-scoped, independently versioned entities. They live in the prompt library and can be reused across multiple workflows by pinning specific versions to input ports. Prompts are referenced by `id` (UUID), never by name.

## Data Model

### Tables

- **`prompt_definitions`** — Org-level prompt identity anchor (id, organization_id). All user-facing metadata lives on versions.
- **`prompt_versions`** — Immutable versioned snapshots. Each version stores name, description, and the full resolved content. Unique constraints: `(prompt_id, version_number)` for version ordering, `(prompt_id, id)` to support composite FK references. Name and description can change between versions. Version creation acquires a `SELECT ... FOR UPDATE` lock on the parent `prompt_definitions` row to serialize concurrent version numbering.
- **`prompt_sections`** — Subprompt composition metadata. Links a parent prompt version to child subprompts via `<<section:placeholder_name>>` syntax. Flat only (one level deep). A composite FK on `(section_prompt_id, section_prompt_version_id)` referencing `prompt_versions(prompt_id, id)` enforces that the pinned section version belongs to the declared section prompt.

### Key Columns

- `port_definitions.is_prompt` — Boolean flag marking which input ports are eligible for prompt library linking (set via `json_schema_extra` in engine component schemas).
- `input_port_instances.prompt_version_id` — Nullable FK to `prompt_versions`. When set, the port is pinned to a library prompt version.

## How Pinning Works

1. User picks a prompt version from the library for an eligible port.
2. Backend sets `InputPortInstance.prompt_version_id` and updates the `FieldExpression.expression_json` to a `LiteralNode` with the version's content.
3. Runtime evaluates the field expression as usual — no special handling needed.
4. When a new version is created, the frontend checks staleness (`pinned_version != latest`) and shows a notification.
5. User clicks "update" → backend sets `prompt_version_id` to the new version and updates the field expression.
6. Unpinning clears `prompt_version_id` to NULL; the field expression retains its current content.

## ParameterKind

`kind` is determined dynamically per `InputPortInstance`:

- `prompt_version_id = NULL` → `kind=INPUT` (full field expression support including `@{{}}`)
- `prompt_version_id = SET` → `kind=PROMPT` (library-pinned, LiteralNode, supports `{{variable}}` only)

The `PortDefinition.is_prompt` flag marks eligibility, not the current state.

## Pin Preservation Through Graph Save

Both V1 and V2 graph save endpoints thread `prompt_version_id` through the parameter conversion path so that create/recreate flows preserve the prompt pin identity. `PipelineParameterV2Schema` carries an optional `prompt_version_id`; `_split_unified_parameters` forwards it to `InputPortInstanceSchema` for `kind=PROMPT` parameters. `_sync_input_port_field_expressions` (V2) and the V1 inline input-param handler both pass `prompt_version_id` to `create_input_port_instance` and `update_input_port_instance`. Cleanup paths skip deletion of prompt-pinned ports (`prompt_version_id IS NOT NULL`).

## Variable Support

Library prompts support `{{variable}}` placeholders filled at runtime by `fill_prompt_template()`. Field expression injection (`@{{}}`) is NOT supported for library prompts.

## Subprompt Composition

A prompt's content can embed other prompts as named sections using `<<section:placeholder_name>>` syntax. The backend resolves all placeholders by inlining the pinned subprompt version's content before storing. `PromptSection` rows are metadata for the frontend. Flat only: subprompts cannot themselves contain `<<section:*>>` references. Section prompts must belong to the same organization as the parent prompt; cross-org references are rejected with `CrossOrgSectionError` (403).

## Diff Strategy

Diffs are computed on-the-fly using `difflib.SequenceMatcher` (character-level opcodes). The API returns both full contents and structured `DiffOperation` objects with character offsets for precise UI highlighting.

## Org-Scoping Enforcement

All prompt and version service functions accept an `organization_id` parameter. When provided, lookups verify that the prompt's `organization_id` matches the URL `org_id` before returning data or mutating state. This prevents IDOR: a user authenticated in org A cannot read, modify, or delete prompts belonging to org B even if they know the prompt UUID. The router always passes `org_id` from the path.

## API Endpoints

### Prompt CRUD (`/orgs/{org_id}/prompts`)

- `POST` — Create prompt with initial version (name, description, content)
- `GET` — List all prompts in org (latest version summary included)
- `GET /{prompt_id}` — Get prompt details + version list
- `DELETE /{prompt_id}` — Delete (fails if still pinned or referenced as a section by other prompts)

### Version Management (`/orgs/{org_id}/prompts/{prompt_id}/versions`)

- `POST` — Create new version (name, description, content, change_description)
- `GET` — List versions
- `GET /{version_id}` — Get version with sections

### Diff (`/orgs/{org_id}/prompts/{prompt_id}/diff?from=&to=`)

### Usages (`/orgs/{org_id}/prompts/{prompt_id}/usages`)

### Pinning

- `PUT /projects/{project_id}/graph/{gr_id}/components/{ci_id}/ports/{port_name}/prompt-pin`
- `DELETE ...` (unpin)
- `GET /projects/{project_id}/prompt-pins` — All pins in project with staleness

Pin/unpin endpoints validate that the graph runner belongs to the specified project via `validate_graph_runner_belongs_to_project` before mutating any port state, preventing cross-project manipulation through forged path parameters. The pin endpoint also verifies that the target port's `PortDefinition.is_prompt` flag is `True`; attempting to pin a prompt to a non-eligible port raises `PortNotPromptEligibleError` (400).

## Git Sync Integration

Prompts can be synced one-way from a GitHub repository. When a repo uses the `draftnrun/` folder convention, markdown files under `draftnrun/prompts/` are imported as prompt definitions. Each subsequent push that modifies a prompt file creates a new version automatically.

- The `git_sync_prompt_mappings` table links each synced `PromptDefinition` to its source file path in the repo.
- Prompt name is derived from the file path relative to `prompts/` (e.g. `folderA/prompt.md` → `folderA/prompt`).
- File format: markdown with optional YAML frontmatter (`description` field). File body = prompt content.
- Sections (`<<section:>>`) are not supported in git-synced prompts.
- Deleted files do not auto-delete prompts (they may still be pinned to ports).

See `ada_backend/docs/git-sync.md` for full details on the folder convention and sync flow.

## Files

- `ada_backend/database/models.py` — `PromptDefinition`, `PromptVersion`, `PromptSection`, `GitSyncPromptMapping` models
- `ada_backend/schemas/prompt_schema.py` — Pydantic schemas
- `ada_backend/repositories/prompt_repository.py` — DB queries
- `ada_backend/repositories/git_sync_repository.py` — Git sync prompt mapping queries
- `ada_backend/services/prompt_service.py` — Business logic
- `ada_backend/services/git_sync_service.py` — Git sync prompt import/sync logic
- `ada_backend/routers/prompt_router.py` — API endpoints
- `ada_backend/utils/prompt_markdown.py` — Markdown frontmatter parser
