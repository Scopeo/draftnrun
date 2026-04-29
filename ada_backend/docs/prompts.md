# Org-Level Prompt Library

## Overview

Prompts are first-class, org-scoped, independently versioned entities. They live in the prompt library and can be reused across multiple workflows by pinning specific versions to input ports.

## Data Model

### Tables

- **`prompts`** — Org-level prompt entity (name, description, organization_id).
- **`prompt_versions`** — Immutable versioned snapshots of prompt content. Each version stores the full resolved text. Unique constraint on `(prompt_id, version_number)`.
- **`prompt_sections`** — Subprompt composition metadata. Links a parent prompt version to child subprompts via `<<section:placeholder_name>>` syntax. Flat only (one level deep).

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

## Variable Support

Library prompts support `{{variable}}` placeholders filled at runtime by `fill_prompt_template()`. Field expression injection (`@{{}}`) is NOT supported for library prompts.

## Subprompt Composition

A prompt's content can embed other prompts as named sections using `<<section:placeholder_name>>` syntax. The backend resolves all placeholders by inlining the pinned subprompt version's content before storing. `PromptSection` rows are metadata for the frontend. Flat only: subprompts cannot themselves contain `<<section:*>>` references.

## Diff Strategy

Diffs are computed on-the-fly using `difflib.SequenceMatcher` (character-level opcodes). The API returns both full contents and structured `DiffOperation` objects with character offsets for precise UI highlighting.

## API Endpoints

### Prompt CRUD (`/orgs/{org_id}/prompts`)

- `POST` — Create prompt with initial version
- `GET` — List all prompts in org
- `GET /{prompt_id}` — Get prompt details + version list
- `PATCH /{prompt_id}` — Update metadata
- `DELETE /{prompt_id}` — Delete (fails if still pinned)

### Version Management (`/orgs/{org_id}/prompts/{prompt_id}/versions`)

- `POST` — Create new version
- `GET` — List versions
- `GET /{version_id}` — Get version with sections

### Diff (`/orgs/{org_id}/prompts/{prompt_id}/diff?from=&to=`)

### Usages (`/orgs/{org_id}/prompts/{prompt_id}/usages`)

### Pinning

- `PUT /projects/{project_id}/graph/{gr_id}/components/{ci_id}/ports/{port_name}/prompt-pin`
- `DELETE ...` (unpin)
- `GET /projects/{project_id}/prompt-pins` — All pins in project with staleness

## Files

- `ada_backend/database/models.py` — `Prompt`, `PromptVersion`, `PromptSection` models
- `ada_backend/schemas/prompt_schema.py` — Pydantic schemas
- `ada_backend/repositories/prompt_repository.py` — DB queries
- `ada_backend/services/prompt_service.py` — Business logic
- `ada_backend/routers/prompt_router.py` — API endpoints
