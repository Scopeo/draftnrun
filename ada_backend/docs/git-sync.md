# Git Sync

One-way sync from a GitHub repository to Draft'n Run. When a user pushes to the configured branch (default `main`), the backend receives a webhook from the GitHub App, fetches the updated graph files (`graph.json` + `<file_key>.json` per component), creates a new versioned graph runner, and deploys it through the same publish path as the frontend: promote to production, then create a fresh draft clone from that promoted graph.

## Architecture

Uses a **GitHub App** (not an OAuth App). The app:

- Receives push webhooks automatically for all repos it's installed on (one global webhook URL)
- Authenticates via JWT + installation access tokens (no Nango, no user OAuth tokens)
- Requires `contents: read` permission only

```text
GitHub repo (push to main)
  → GitHub App fires webhook to POST /webhooks/github
  → Backend verifies HMAC with GITHUB_APP_WEBHOOK_SECRET
  → Backend looks up matching GitSyncConfig by (owner, repo_name, branch)
  → For each matching config where graph files changed, enqueue a Redis job
  → Webhook returns immediately (non-blocking)
  → Git sync queue worker picks up the job:
    → Generates an installation token (JWT → installation access token)
    → Fetches graph.json + <file_key>.json per component via GitHub Contents API
    → Creates a new graph runner, populates it with the graph JSON
    → Calls the standard deploy service used by frontend publish
    → Deployed runner becomes production (tagged), and a new draft clone is created from it
```

## Data Model

`git_sync_configs` table:

- `github_owner` — GitHub repository owner (user or organization name)
- `github_repo_name` — GitHub repository name
- `graph_folder` — folder path in the repo containing `graph.json` and per-component `<file_key>.json` files (auto-detected at setup time)
- `branch` — branch to watch (default `main`)
- `github_installation_id` — GitHub App installation ID (integer, from the installation event)
- `last_sync_status` — status of the last sync attempt (`success`, `fetch_failed`, `update_failed`, `deploy_failed`)
- `last_sync_error` — human-readable error message from the last failed sync (cleared on success)
- `last_sync_commit_sha` — SHA of the commit that triggered the last sync

Unique constraints: `(github_owner, github_repo_name, graph_folder, branch)` — one sync config per repo/folder/branch combination; `(project_id)` — one sync config per project.

A single repo can host multiple projects (one graph payload per subfolder), all in the same organization.

## GitHub App Setup

1. Create a GitHub App at github.com → Settings → Developer settings → GitHub Apps → New
2. Configure:
   - **Webhook URL**: `{ADA_URL}/webhooks/github`
   - **Webhook secret**: generate a random string, set as `GITHUB_APP_WEBHOOK_SECRET` env var
   - **Permissions**: Repository contents → Read-only
   - **Events**: Subscribe to `Push` events
3. After creation, note the **App ID** → set as `GITHUB_APP_ID` env var
4. Generate a **private key** → set the PEM contents as `GITHUB_APP_PRIVATE_KEY` env var
5. Users install the app on their repos via the GitHub App's installation page

## GitHub App Auth Flow

1. Backend signs a JWT with the App's private key (RS256, valid 10 min)
2. Exchanges the JWT for an installation access token via `POST /app/installations/{id}/access_tokens`
3. Uses the installation token (valid ~1 hour) to call the GitHub API

This happens automatically on each webhook — no user interaction needed.

## Setup Flow

1. User installs the GitHub App on their repo (via GitHub UI)
2. The installation ID is provided to Draft'n Run (from the GitHub App install page or via API)
3. User calls `POST /organizations/{org_id}/git-sync` (or MCP tool `configure_git_sync`) with `github_owner`, `github_repo_name`, `branch`, `github_installation_id`, and optionally `project_type`
4. Backend scans the repo tree (Git Trees API, recursive) for all `graph.json` files
5. For each folder containing a `graph.json` that doesn't already have a sync config, the backend creates a new project (named after the folder, or the repo name for root-level) with a `"github"` tag and a `GitSyncConfig` row
6. Backend enqueues an initial sync job for each new config — the existing `graph.json` is deployed immediately using the standard deploy flow (best-effort: if enqueue fails, subsequent pushes will trigger syncs normally)

MCP tools: `configure_git_sync`, `list_git_sync_configs`, `get_git_sync_config`, `disconnect_git_sync` (see `docs://admin`).

## Service Contract

- `import_from_github` returns typed `GitSyncImportResult` items plus `skipped` folder names.
- Routers should pass those typed items through `GitSyncImportResponse` directly.

## Sync Flow (on push)

1. GitHub sends `POST /webhooks/github` with signed payload
2. Backend verifies HMAC signature using `GITHUB_APP_WEBHOOK_SECRET` (global, one secret for all)
3. Looks up matching `git_sync_configs` by `(github_owner, github_repo_name, branch)`
4. For each matching config where any file in the tracked folder changed (subfolder prefix match for non-root configs, root-level files only for root configs), enqueues a job to the `ada_git_sync_queue` Redis queue and returns immediately. Enqueue is idempotent per `(config_id, commit_sha)` via a Redis `SET NX` dedup key (TTL 1 hour), so webhook retries (e.g. on partial enqueue failure returning 502) never produce duplicate queue entries
5. The `GitSyncQueueWorker` (daemon thread in the API process) picks up each job and:

   - Loads the config from DB
   - Generates an installation token
   - Fetches graph.json + <file_key>.json per component via GitHub Contents API
   - Creates a new graph runner and populates it from the payload
   - Calls the canonical deploy flow (tag + production promotion + fresh draft clone)
   - Updates `last_sync_status` and `last_sync_error` (human-readable error message on failure, cleared on success)

## Graph Payload Format

File-based format with one file per component, all in the same folder:
- `graph.json` contains topology (`nodes`, `edges`, `relationships`); nodes reference components by `file_key`
- `<file_key>.json` contains per-component payload (`component_id`, `component_version_id`, `parameters`, `input_port_instances`, etc.)
- Edges and field expression refs use `file_key` (e.g. `{"type": "ref", "file_key": "start", "port": "output"}`); the mapper resolves them to server-generated UUIDs at sync time
- No hardcoded instance IDs needed — all IDs are generated fresh on each sync

## Disconnect

`DELETE /organizations/{org_id}/git-sync/{config_id}` deletes the `GitSyncConfig` row. The GitHub App installation remains (managed by the user on GitHub).

## Security

- Webhook endpoint is public — secured by HMAC-SHA256 with `GITHUB_APP_WEBHOOK_SECRET`
- One global webhook secret (configured when creating the GitHub App)
- Installation tokens are short-lived (~1 hour), generated on-demand
- No tokens stored in the database
- Setup/management endpoints require DEVELOPER role via standard auth

## Frontend Integration

The Integrations page (`connections.vue`) includes a GitHub card when `GITHUB_APP_SLUG` is configured.

Flow:
1. User clicks "Connect" → popup opens to `https://github.com/apps/{slug}/installations/new`
2. After installation, GitHub redirects to the app's Setup URL (must be configured to `{FRONTEND_URL}/github/callback`)
3. The callback page posts the `installation_id` back to the opener via `postMessage`
4. A repo-picker dialog appears listing accessible repos (`GET /{org_id}/git-sync/installations/{id}/repos`)
5. User selects a repo → `POST /{org_id}/git-sync` imports matching graph payloads

API endpoints added for the frontend:
- `GET /{org_id}/git-sync/github-app` — returns `{ configured, install_url }` (requires `GITHUB_APP_SLUG`)
- `GET /{org_id}/git-sync/installations/{installation_id}/repos` — proxies `list_installation_repos`

## Env Vars

| Var | Description |
| --- | --- |
| `GITHUB_APP_ID` | App ID from the GitHub App settings page |
| `GITHUB_APP_SLUG` | URL slug of the GitHub App (from `github.com/apps/{slug}`) |
| `GITHUB_APP_PRIVATE_KEY` | PEM private key (contents, not file path) |
| `GITHUB_APP_WEBHOOK_SECRET` | Webhook secret configured on the GitHub App |

## Dependencies

Requires the `PyJWT` package with cryptography extras (`PyJWT[crypto]`) for RS256 JWT signing.
