---
description: Draft'n Run frontend architecture — directory layout, component patterns, API and data-fetching conventions
globs: ['src/**']
alwaysApply: false
---

# Back-office architecture

## Directory structure

```
src/
  api/              # Domain-specific API modules (one file per domain)
  assets/           # Images, styles (auth.scss, misc.scss)
  components/       # Reusable components
    charts/         #   Chart.js wrappers (BarChart, LineChart, etc.)
    dialogs/        #   GenericConfirmDialog, HelpRequestDialog
    shared/         #   EmptyState, ErrorState, skeletons, VersionSelector, etc.
    studio/         #   Studio/flow builder (Vue Flow nodes, edges, panels)
    knowledge/      #   Knowledge base CRUD & editor
    monitoring/     #   Monitoring/observability dashboards
    qa/             #   QA testing & evaluation
    workflows/      #   Workflow-specific UI
    agents/         #   Agent-specific UI
    observability/  #   Observability detail views
  composables/      # Vue composables
    queries/        #   TanStack Query hooks (one per domain)
  layouts/          # default.vue (sidebar + main), blank.vue (auth pages)
  navigation/       # Sidebar nav item config (vertical/)
  pages/            # File-based routing (unplugin-vue-router)
  plugins/          # App plugins (vuetify, casl, router, gtm, hotjar)
  services/         # Backend integration (auth, Google Drive, scopeoApi barrel)
  stores/           # Pinia stores — auth, org, config (only these three)
  types/            # TypeScript type definitions
  utils/            # Helpers (logger, colorConverter, validators, formatters, etc.)
```

## Component conventions

- **Naming:** PascalCase file names (`AgentChatHistory.vue`).
- **Max size:** ~400 lines per `.vue` file. Extract sub-components or composables when approaching the limit.
- **Script:** Always `<script setup lang="ts">`.
- **Props/Emits:** Use generic type parameter syntax (`defineProps<T>()`, `defineEmits<T>()`).

## API modules (`src/api/`)

One file per domain — e.g. `agents.ts`, `workflows.ts`, `knowledge.ts`.
Each exports named API objects (e.g. `export const agentsApi = { ... }`).

`src/api/index.ts` re-exports everything individually AND as a `scopeoApi` barrel for backward compatibility.
New code should import domain-specific APIs directly (`import { agentsApi } from '@/api/agents'`).

## Data fetching — TanStack Query

All server reads go through composables in `src/composables/queries/`.
One file per domain (e.g. `useAgentsQuery.ts`, `useProjectsQuery.ts`).

Rules:
- All server state managed via TanStack Query — never manual `ref` for API data.
- `queryKey` must be a computed array for cache management.
- Use `enabled: computed(...)` for conditional fetching.
- Inline edits: patch cache with `setQueryData` (no `invalidateQueries`).
- Destructive/structural changes: `invalidateQueries` is acceptable.
- Slow APIs: optimistic updates via `onMutate` + `onError` rollback.

## State management — Pinia

Only three stores:
- `auth` — user session, login/logout
- `org` — current organization context
- `config` — theme (light/dark/system), nav collapsed state

Do not create new stores for server data — use TanStack Query composables.

## Naming conventions

- "Workflow" and "Project" are used interchangeably in the UI. Backend calls them "workflows"; the frontend routes and some components use "projects".
- Agent = a workflow with exactly one component.

## Layout

- **Default layout:** `VNavigationDrawer` sidebar (`AppSidebar.vue`) + `VMain` content area. No global top bar.
- **Blank layout:** Used for auth pages (login, register, forgot-password, etc.).
- Sidebar supports rail (collapsed) mode, persisted in config store.
- Nav items defined in `src/navigation/vertical/`.

## Icons

Use Iconify with `tabler` as the primary icon set.
Additional sets available: `mdi`, `ph`, `fa`, `logos`.
Import via `@iconify/vue` `<Icon>` component.

## Routing

File-based routing via `unplugin-vue-router`.
Org-scoped pages live under `src/pages/org/[orgId]/`.
Auth pages live under `src/pages/auth/` and `src/pages/` root.
Route guards use CASL `canNavigate()`.
