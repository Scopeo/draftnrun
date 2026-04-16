# Draft'n Run — Frontend

Vue 3 + Vuetify SaaS back-office for a no-code workflow and agent builder.
Desktop-only (no mobile/tablet).

- **Package:** `draftnrun-frontend` v1.0.0
- **Production:** [app.draftnrun.com](https://app.draftnrun.com)

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

### Prerequisites

- Node 18+
- pnpm 8+

### Setup

```bash
pnpm install
cp .env.example .env   # fill in values
pnpm dev               # dev server at localhost:5173
```

### Scripts

| Command         | Description                |
| --------------- | -------------------------- |
| `pnpm dev`      | Start dev server           |
| `pnpm build`    | Production build           |
| `pnpm preview`  | Preview production build   |
| `pnpm test`     | Run tests (Vitest)         |
| `pnpm typecheck`| Type-check without emit    |
| `pnpm lint`     | Lint with ESLint           |
| `pnpm format`   | Format with Prettier       |
| `pnpm fix`      | Format + lint              |

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

## Deployment

| Target     | Platform |
| ---------- | -------- |
| Production | Netlify  |
| Local      | Docker   |

For Sentry source map uploads during build, set `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_PROJECT` environment variables.
