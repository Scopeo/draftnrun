# Draft'n Run — Frontend

Vue 3 + Vuetify SaaS back-office for a no-code workflow and agent builder.
Desktop-only (no mobile/tablet).

- **Package:** `draftnrun-frontend` v1.0.0

## Tech stack

| Layer          | Technology                                   |
| -------------- | -------------------------------------------- |
| Framework      | Vue 3.5, TypeScript 5.7                      |
| UI             | Vuetify 3.7                                  |
| State          | Pinia (local), TanStack Vue Query (server)   |
| Build          | Vite 5                                       |
| Auth           | Supabase                                     |
| Authorization  | CASL (`@casl/ability` + `@casl/vue`)         |
| Monitoring     | Sentry, Hotjar, GTM                          |
| Editors        | TipTap (rich text), Vue Flow (graph), CodeMirror |
| Charts         | Chart.js + vue-chartjs                       |
| Icons          | Iconify (tabler, mdi, ph, fa, logos) + custom brand SVGs |
| Fonts          | DM Sans + Source Serif 4 (`@fontsource/*`)   |
| Testing        | Vitest                                       |

## Directory structure

```
src/
  api/              # Domain-specific API modules (split from monolithic scopeoApi)
  assets/           # Images, styles (auth.scss, misc.scss)
    images/iconify-svg/ # Custom brand SVGs auto-registered as custom:* icons
    images/svg/         # Vuetify form-control SVG overrides (checkbox, radio)
  components/       # Reusable components
    charts/         #   Chart.js wrapper components
    dialogs/        #   Dialog components (GenericConfirmDialog, HelpRequestDialog)
    shared/         #   Shared patterns (EmptyState, ErrorState, skeletons, etc.)
    studio/         #   Studio/flow builder components
    knowledge/      #   Knowledge base components
    monitoring/     #   Monitoring/observability components
    qa/             #   QA testing components
    workflows/      #   Workflow-specific components
    agents/         #   Agent-specific components
    observability/  #   Observability components
  composables/      # Vue composables
    queries/        #   TanStack Query hooks (one per domain)
  layouts/          # Layout system (default.vue, blank.vue, AppSidebar)
  navigation/       # Nav item configuration
  pages/            # File-based routing (unplugin-vue-router)
  plugins/          # App plugins (vuetify, casl, router, gtm, hotjar)
  services/         # Backend integration (auth, googleDrive)
  stores/           # Pinia stores (auth, org, config)
  types/            # TypeScript type definitions
  utils/            # Utility functions (logger, colorConverter, validators, etc.)
```

## Getting started

> All commands below are run from the `frontend/` directory of the monorepo:
>
> ```bash
> cd frontend
> ```

### Prerequisites

- Node 18.18+
- pnpm 8+ (`corepack enable` then `corepack prepare pnpm@8.15.3 --activate`)
- Docker + Docker Compose (only required for the prod-on-local-server flow)

### Install

```bash
pnpm install
cp .env.example .env   # fill in values — see "Environment variables" below
```

## Running the frontend

There are **two** ways to run the frontend locally, and they are **not interchangeable**.
Pick the one that matches what you're trying to do.

### 1. Development mode — `pnpm dev`

Use this **only** while writing code on your laptop. It runs the Vite dev server with hot module replacement, source maps, no minification, and dev-only warnings — it is **not** a production server.

```bash
pnpm dev          # http://localhost:5173
```

> ⚠️ **`pnpm dev` is not a production server.**
> The dev server is unbundled, single-process, and exposes dev tooling. It exists to give you fast feedback while editing code — nothing else. Never use it to host the app for anyone (yourself included) as a "prod-like" environment, even on `localhost`. Build and serve the static bundle instead — see below.

### 2. Production build, served locally

This is the right way to run "prod on a local server." It produces a real production bundle (minified, tree-shaken, hashed asset filenames) and serves the resulting static files. Pick whichever option you prefer.

**Option A — `pnpm build && pnpm preview` (simplest, no Docker):**

```bash
pnpm build        # produces frontend/dist/
pnpm preview      # http://localhost:5050 — serves dist/ as static files
```

**Option B — Docker + nginx (containerized, closer to a real deploy):**

```bash
docker compose -f docker-compose.prod.yml up --build
# http://localhost:8080
```

This uses [`prod.Dockerfile`](./prod.Dockerfile) — a multi-stage build that runs `pnpm build` and copies `dist/` into an `nginx:stable-alpine` image configured by [`nginx.conf`](./nginx.conf) (with SPA fallback to `index.html`).

Either way, this is what real users get, just running on your machine. If something works in `pnpm dev` but breaks here, that's a real bug — fix it before shipping.

> ❌ `pnpm dev` is **not** "prod on a local server." If you're tempted to run `pnpm dev` and call it production, stop and run one of the two options above instead.

### Scripts reference

| Command          | Use it for                                                  |
| ---------------- | ----------------------------------------------------------- |
| `pnpm dev`       | Local development only (hot reload, unbundled)              |
| `pnpm build`     | Produce a production bundle in `dist/`                      |
| `pnpm preview`   | Serve `dist/` locally on `:5050` for a quick smoke test     |
| `pnpm test`      | Run tests (Vitest)                                          |
| `pnpm typecheck` | Type-check without emit                                     |
| `pnpm lint`      | Lint with ESLint                                            |
| `pnpm format`    | Format with Prettier                                        |
| `pnpm fix`       | Format + lint                                               |

### Environment variables

See `.env.example` for the full list. Key groups:

- **Supabase** — `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
- **Backend API** — `VITE_SCOPEO_API_URL`
- **Google OAuth** — login, Drive, and Gmail client IDs/secrets
- **Sentry** — `VITE_SENTRY_DSN`, `VITE_SENTRY_ENVIRONMENT`
- **Sentry source maps** — `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` (build-time)
- **GTM** — `VITE_GTM_ID`
- **Stripe** — `VITE_STRIPE_PUBLISHABLE_KEY`
- **Feature flags** — `VITE_ENABLE_CHAT_HISTORY` (set to `true` only when `chat_history` backend tables/RPCs are configured)

## Architecture

### Authentication

Supabase auth with a Pinia store (`stores/auth.ts`) + `localStorage`.
`AuthProvider.vue` wraps the app and guards authenticated routes.
Password reset uses Supabase recovery links (`resetPasswordForEmail`) and the `/reset-password` page exchanges the recovery hash for a session before allowing password update.

### Invitation flow

Organization invites are handled through `/accept-invite`.
When an invite token is present, login/register screens switch to invite-safe mode (no social auth shortcuts) and the accept-invite page fetches and displays invite context (organization, role, invited email).

### API layer

Each domain has its own module in `src/api/` (e.g. `agents.ts`, `workflows.ts`, `knowledge.ts`).
A namespace object `scopeoApi` in `src/api/index.ts` re-exports all domain APIs under a single import.

### Data fetching

All server reads go through TanStack Query composables in `src/composables/queries/`.
One file per domain (e.g. `useAgentsQuery.ts`, `useProjectsQuery.ts`).
Mutations use `useMutation` with cache patching (`setQueryData`) for inline edits
and `invalidateQueries` only for destructive/structural changes.

### Logging

Centralized `logger` in `src/utils/logger.ts` with Sentry integration.
Use `logger.info/warn/error()` everywhere — never bare `console.*`.

### Notifications

Global toast system via `useNotifications()` composable, rendered by `AppNotifications.vue` in the default layout.

### Authorization

CASL with `canNavigate()` for route guards.
Ability rules defined in `src/utils/abilityRules.ts`.

### Theme

Config store (`stores/config.ts`) with light/dark/system cycling.
Color and typography defaults: `src/plugins/vuetify/theme.ts` and `src/plugins/vuetify/defaults.ts`.
Layout and spacing CSS variables plus global Vuetify polish (e.g. pill tab label size): `src/assets/styles/variables/_tokens.scss`.
Primary color: `#22577A`.

### Layout

`VNavigationDrawer` sidebar (`AppSidebar.vue`) with collapsible rail mode.
No global top bar — navigation lives entirely in the sidebar.

## Sentry source maps (optional)

To upload source maps to Sentry during `pnpm build`, set `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_PROJECT` in your environment. If unset, the build skips the upload step and still produces a working bundle.
