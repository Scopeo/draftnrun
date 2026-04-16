---
name: Vuexy Removal Plan
overview: Remove all Vuexy proprietary code (@core, @layouts, fake-api, SCSS, branding) while keeping Vuetify (MIT-licensed). Includes dead code purge, SCSS cleanup, infrastructure rewrites (auth store, CASL, logger, i18n, API split, data fetching architecture), layout rebuild, entity page deduplication, component decomposition, tests, and documentation.
todos:
  - id: phase-0-foundation
    content: "Phase 0: Clean up Vuetify plugin, replace registerPlugins, clean vite.config, polish theme, add Inter font, rename package.json"
    status: completed
  - id: phase-1-purge
    content: "Phase 1: Extract needed utils, delete @core/ @layouts/ fake-api/, 15 dead dialogs, dead components, SCSS cleanup, branding sweep, ~28 npm packages"
    status: completed
  - id: phase-2-auth
    content: "Phase 2a: Build Pinia auth store with localStorage, replace all useCookie calls (~21 across auth.ts, guards.ts, org.ts, pages)"
    status: completed
  - id: phase-2-casl
    content: "Phase 2b: Relocate CASL navigation helpers from @layouts to src/plugins/casl/navigation.ts"
    status: completed
  - id: phase-2-config
    content: "Phase 2c: Build slim theme config store (~40 lines) with Vuetify useTheme() integration"
    status: completed
  - id: phase-2-logger
    content: "Phase 2d: Create logger.ts with Sentry integration, replace ~100+ console.log/warn/error"
    status: completed
  - id: phase-2-i18n
    content: "Phase 2e: Remove i18n entirely (delete plugin, replace $t() calls, remove VLocaleProvider)"
    status: completed
  - id: phase-2-utils
    content: "Phase 2f: Verify relocated @core utilities compile (colorConverter, chartConfig, validators)"
    status: completed
  - id: phase-2-api
    content: "Phase 2g: Split scopeoApi.ts (1,088 lines) into 16 domain modules in src/api/"
    status: completed
  - id: phase-2-icons
    content: "Phase 2h: Rebuild icon system plugin with lazy-loading, without @core dependency"
    status: completed
  - id: phase-2-data-fetching
    content: "Phase 2i: Data fetching architecture cleanup -- establish TanStack Query conventions, create missing composables (useGraphQuery, useApiKeysQuery, useOrganizationSecretsQuery), document patterns for future WebSocket readiness"
    status: completed
  - id: phase-3-unwrap
    content: "Phase 3: Replace @core wrapper components with plain Vuetify (~10 live files), write auth/error page CSS replacements"
    status: completed
  - id: phase-4-layout
    content: "Phase 4: Rebuild layout (VNavigationDrawer sidebar, entity header with breadcrumb+tabs, collapsible independent floating panels, navigation composable, unified toast system)"
    status: completed
  - id: phase-5-patterns
    content: "Phase 5-pre: Build shared UI patterns (skeleton templates, EmptyState, ErrorState components)"
    status: completed
  - id: phase-5-pages
    content: "Phase 5a-d: Migrate all pages (remove @core/@layouts, remove hardcoded creds, use logger, use notifications, add skeletons/empty states)"
    status: completed
  - id: phase-5-dedup
    content: "Phase 5e: Extract shared EntityDetailPage, fix agents/[id].vue to use useAgentQuery, add list-to-detail prefetching"
    status: completed
  - id: phase-5-decompose
    content: "Phase 5f: Decompose large components + fix data fetching (SharedPlayground use query hooks, StudioFlow use useGraphQuery, Organization use secrets/apikeys queries, consolidate ApiKeys/SharedAPI)"
    status: completed
  - id: phase-5-charts-shared
    content: "Phase 5g-h: Relocate chart wrappers, migrate tippy.js (2 files), rebuild shared components"
    status: completed
  - id: phase-6-cleanup
    content: "Phase 6: Remove leftover aliases, dead packages, stylelint, dead CSS, final branding verification, verify build"
    status: completed
  - id: phase-7-tests
    content: "Phase 7: Tests for auth flow, navigation, theme, API modules, extracted composables, smoke tests"
    status: completed
  - id: phase-8-docs
    content: "Phase 8: Rewrite README, create cursor rules (architecture, styling, practices)"
    status: completed
isProject: false
---

# Vuexy Proprietary Code Removal

## Context

Draft'n Run's back-office is a Vue 3 frontend for a no-code workflow and agent builder. It was originally scaffolded with **Vuexy**, a paid proprietary template by Pixinvent built on top of **Vuetify** (an MIT-licensed open-source component library).

**Goal:** Remove all Vuexy proprietary code -- including source files, SCSS, branding, and dependencies -- so the project no longer depends on the Vuexy license. Vuetify itself is MIT-licensed and stays as the component library.

**Key decisions:**

- Vuetify stays (MIT, no license concern). No Tailwind. No custom UI component library.
- VDataTable stays (no TanStack Vue Table migration needed).
- moment.js stays (not Vuexy code, out of scope for this work).
- English only (drop i18n entirely).
- "Workflow" for workflow-specific things, "project" for things concerning both agents and workflows.
- Package renamed to `draftnrun-frontend` version `1.0.0`.
- Design direction: minimalist, modern, tech. Primary color `#22577A` kept. Inter font.
- No backward compatibility: simple and clean wins.
- Desktop-only (no mobile/tablet responsiveness needed).
- 6 developers, tens of users. Deployed on Netlify (prod) + Docker (local).

## Current State

- **139 files** in `src/@core/` -- Vuexy proprietary core (components, composables, SCSS, utilities)
- **29 files** in `src/@layouts/` -- Vuexy proprietary layout system (nav, stores, config)
- **36 files** in `src/plugins/fake-api/` -- Vuexy demo mock data (already no-op)
- **~5,853 lines** of proprietary Vuexy SCSS (Vuetify component overrides, layout styles, skin system, route transitions)
- **15 dead dialog components**, **19 dead @core components** -- Vuexy demos never used
- **5 giant components** to decompose: EditSidebar (3,365 lines), SharedPlayground (3,151), QADatasetTable (2,507), StudioFlow (2,009), Organization settings (1,100+)
- **1,088-line monolith API** (`scopeoApi.ts`) to split into domain modules
- **~80% code duplication** between workflow and agent detail pages
- Cookie-based auth state (`useCookie`) to replace with Pinia store + localStorage
- ~100+ `console.log` statements to replace with structured logger
- Hardcoded test credentials in `login.vue` (security concern)
- Unusual navigation initialization pattern (async function with watchers outside composable scope)
- Vuexy branding in `package.json` (`"name": "vuexy-vuejs-admin-template"`), `index.html` (localStorage keys `vuexy-initial-loader-bg` / `vuexy-initial-loader-color`), and dead dialog components
- Inconsistent data fetching: 19 TanStack Query composables exist but ~12 components bypass them with direct `scopeoApi` calls (duplicate fetches, no caching, no deduplication). Zero prefetching. Agent detail page doesn't use its own query hook.
- **Broken Sentry**: No source maps uploaded (errors show minified code), `tracePropagationTargets` uses Sentry's placeholder regex (`yourserver.io`), zero `Sentry.setUser()` calls (can't identify users), zero `Sentry.captureException()` in catch blocks (caught errors invisible), no `ignoreErrors` filter (browser extension noise).

## Dependency Audit

**REMOVE (confirmed unused or Vuexy-only):**

- Vuexy template deps: `roboto-fontface`, `webfontloader`, `cookie-es`, `vue3-perfect-scrollbar`
- Vuexy demo deps: `vue3-apexcharts`, `apexcharts`, `@fullcalendar/`* (6 packages), `swiper`, `mapbox-gl`, `vue-prism-component`, `prismjs`, `@videojs-player/vue`, `video.js`, `shiki`
- Unused libraries: `vue-shepherd`, `shepherd.js`, `@formkit/drag-and-drop`, `vue-json-viewer`, `vue-flatpickr-component`, `@sindresorhus/is`, `jwt-decode`, `@floating-ui/dom`, `@vueuse/math`, `msw`
- Being replaced: `vue-i18n`, `@intlify/unplugin-vue-i18n`, `tippy.js`
- Linting (no custom SCSS left): `stylelint`, `stylelint-config-idiomatic-order`, `stylelint-config-standard-scss`, `stylelint-use-logical-spec`, `@stylistic/stylelint-config`, `@stylistic/stylelint-plugin`

**KEEP:**

- Core: `vue`, `vue-router`, `pinia`, `vuetify`, `vite-plugin-vuetify`
- Data: `@tanstack/vue-query`, `ofetch`, `moment` (out of scope)
- Auth: `@supabase/supabase-js`, `@casl/ability`, `@casl/vue`
- Monitoring: `@sentry/vue`, `chart.js`, `vue-chartjs`
- Editors: `@vue-flow/`*, `@tiptap/`*, `@codemirror/*`
- Utilities: `@vueuse/core`, `@iconify/vue`, `@iconify-json/*`, `date-fns`, `lodash-es`, `uuid`, `gpt-tokenizer`, `cronstrue`, `highlight.js`, `markdown-it`, `dagre`
- Services: `src/services/googleDrive.ts` (used, awaiting menu validation)

**ADD:** `@fontsource/inter`, `@sentry/vite-plugin` (dev dependency -- source map upload on build)

---

## Phase 0 -- Foundation

### 0.1 Clean Up Vuetify Plugin

`[src/plugins/vuetify/index.ts](src/plugins/vuetify/index.ts)` currently depends on Vuexy internals: `@themeConfig`, `@layouts/stores/config` (cookieRef), `vue-i18n` locale adapter, and `@core/scss`. Rewrite to:

- Remove `cookieRef` usage (dynamic primary colors from cookies) -- use static theme values
- Remove `vue-i18n` locale adapter (i18n is being removed entirely)
- Remove `@core/scss/template/libs/vuetify/index.scss` import -- rely on stock Vuetify styles
- Remove `@themeConfig` import
- Keep the `IconBtn` alias (useful shorthand for icon buttons), `defaults`, `icons`, and `themes`

`[src/plugins/vuetify/defaults.ts](src/plugins/vuetify/defaults.ts)`: Keep as-is. Remove `app-autocomplete__content`, `app-inner-list`, `app-select__content` CSS class references from `VAutocomplete`/`VSelect`/`VCombobox` `menuProps` (those classes come from deleted @core SCSS).

`[src/plugins/vuetify/theme.ts](src/plugins/vuetify/theme.ts)`: Keep and polish. Light theme primary stays `#22577A`. Dark theme primary is currently `#42A5F5` (lighter blue for readability on dark backgrounds) -- review if this should stay or align with brand. Clean up Vuexy-specific color keys (`perfect-scrollbar-thumb`, `skin-bordered-`*, `expansion-panel-text-custom-bg`). Modernize palette if desired (subtle surface tones, refined shadows).

### 0.2 Font System

Remove `roboto-fontface` and `webfontloader` packages. Add `@fontsource/inter` and import in main entry. Ensure Vuetify uses Inter via theme typography config.

### 0.3 Replace Plugin Registration

`[src/main.ts](src/main.ts)` imports `registerPlugins` from `@core/utils/plugins` -- a glob-based auto-import that scans `src/plugins/`. Replace with explicit imports for clarity:

```typescript
import vuetifyPlugin from '@/plugins/vuetify'
import routerPlugin from '@/plugins/1.router'
import caslPlugin from '@/plugins/casl'
```

Also in `main.ts`: remove `@core/scss/template/index.scss` import, remove dead `console.log` statements and unused `userData` parsing block.

### 0.4 Vite Config Cleanup

In `[vite.config.ts](vite.config.ts)`:

- Remove aliases: `@configured-variables`, `@db`, `@api-utils`, `@themeConfig`
- Remove `@core` and `@layouts` aliases (after all code is migrated in later phases)
- Remove `@intlify/unplugin-vue-i18n` plugin
- Update `unplugin-vue-components` dirs: remove `src/@core/components`
- Update `unplugin-auto-import` dirs: remove all `@core` paths
- Keep `vite-plugin-vuetify`

### 0.5 Rename package.json

- `"name": "draftnrun-frontend"` (currently `"vuexy-vuejs-admin-template"`)
- `"version": "1.0.0"`

---

## Phase 1 -- Dead Code Purge

Delete everything confirmed unused before touching live code. All Vuexy SCSS is proprietary and must be fully removed, not just orphaned by deleting directories.

### 1.1 Extract Before Deletion

Before deleting `@core/` and `@layouts/`, extract files needed by live code:

- `@core/utils/colorConverter.ts` to `src/utils/colorConverter.ts`
- `@core/libs/chartjs/chartjsConfig.ts` to `src/utils/chartConfig.ts`
- `@core/libs/chartjs/*.vue` (7 chart wrapper components) to `src/components/charts/`
- `@layouts/plugins/casl.ts` to `src/plugins/casl/navigation.ts`
- `CustomRadios.vue` and `CustomRadiosWithIcon.vue` to `src/components/shared/`
- Audit `@core/utils/validators.ts`, `formatters.ts`, `helpers.ts` -- merge any actively used parts into `src/utils/`

### 1.2 Delete Entire Directories

- `src/@core/` (139 files) -- Vuexy proprietary core
- `src/@layouts/` (29 files) -- Vuexy proprietary layout system
- `src/plugins/fake-api/` (36 files) -- Vuexy demo mock data
- `src/plugins/i18n/` -- i18n plugin + locale files
- `src/plugins/iconify/` -- will be rebuilt from scratch
- `src/views/` (AuthProvider.vue, unused)
- `src/navigation/horizontal/` -- unused horizontal nav config

### 1.3 Delete Unused Files

- `src/plugins/webfontloader.ts` -- replaced by @fontsource/inter
- `src/plugins/layouts.ts` -- Vuexy layout plugin wrapper
- `src/composables/useApi.ts` -- deprecated legacy fetch wrapper (zero imports)
- `src/composables/useAgents.ts` -- deprecated, replaced by TanStack Query hooks
- `themeConfig.ts` -- Vuexy theme config (root level)
- `src/utils/paginationMeta.ts` -- only used in deleted code

### 1.4 Delete Dead Components

15 dead dialog components (Vuexy demos, zero live usage). **Note:** `GenericConfirmDialog.vue` is heavily used (13+ live components) and is NOT deleted.

Dead dialogs to delete:
`AddAuthenticatorAppDialog.vue`, `AddEditAddressDialog.vue`, `AddEditPermissionDialog.vue`, `AddEditRoleDialog.vue`, `AddPaymentMethodDialog.vue`, `CardAddEditDialog.vue`, `ConfirmDialog.vue` (Vuexy subscription-cancel demo -- only used by the also-dead `UserUpgradePlanDialog`), `CreateAppDialog.vue`, `EnableOneTimePasswordDialog.vue`, `PaymentProvidersDialog.vue`, `PricingPlanDialog.vue`, `ReferAndEarnDialog.vue`, `ShareProjectDialog.vue`, `TwoFactorAuthDialog.vue`, `UserInfoEditDialog.vue`, `UserUpgradePlanDialog.vue`

Dead application components:

- `AppPricing.vue` -- unused
- `MagicalWorkflowBuilder.vue` (2,490 lines) -- confirmed dead code
- `src/pages/try-builder.vue` -- only consumer of MagicalWorkflowBuilder
- `src/pages/builder-minimal.vue` -- only consumer of MagicalWorkflowBuilder
- `src/pages/customer/index.vue` -- Vuexy mock demo page
- `src/pages/access-control.vue` -- Vuexy demo page

### 1.5 Vuexy SCSS Cleanup

All Vuexy SCSS is proprietary code. Deleting `@core/` removes the source files, but references to them throughout the codebase must also be cleaned up or the build will break silently.

**Imports to remove from `main.ts`:**

- `import '@core/scss/template/index.scss'` -- main Vuexy SCSS entry point (~5,853 lines of proprietary overrides)

**SCSS files to delete (they `@forward` into deleted @core SCSS):**

- `src/assets/styles/variables/_vuetify.scss` -- `@forward '../../../@core/scss/template/libs/vuetify/variables'`
- `src/assets/styles/variables/_template.scss` -- `@forward '@core/scss/template/variables'`
- `src/assets/styles/styles.scss` -- empty file (comment says "Write your overrides", references @core variables)

**Page-level SCSS imports to remove (will break if left):**

- `src/pages/login.vue` -- `@use '@core/scss/template/pages/page-auth'`
- `src/pages/register.vue` -- `@use '@core/scss/template/pages/page-auth'`
- `src/pages/forgot-password.vue` -- `@use '@core/scss/template/pages/page-auth'`
- `src/pages/reset-password.vue` -- `@use '@core/scss/template/pages/page-auth'`
- `src/pages/verify-email.vue` -- `@use '@core/scss/template/pages/page-auth'`
- `src/pages/not-authorized.vue` -- `@use '@core/scss/template/pages/misc.scss'`
- `src/pages/[...error].vue` -- `@use '@core/scss/template/pages/misc.scss'`

**Replacement:** Write minimal CSS replacements in `src/assets/styles/auth.scss` (~~30 lines: centered card, max-width, vertical centering) and `src/assets/styles/misc.scss` (~~15 lines: centered error/info layout). Import these in the affected pages.

**Stylelint removal (no custom SCSS left to lint):**

- Delete `.stylelintrc.json`
- Remove stylelint references from `.vscode/settings.json` and `.cursor/settings.json`
- Remove stylelint from `.vscode/extensions.json`
- Remove npm packages: `stylelint`, `stylelint-config-idiomatic-order`, `stylelint-config-standard-scss`, `stylelint-use-logical-spec`, `@stylistic/stylelint-config`, `@stylistic/stylelint-plugin`

### 1.6 Vuexy Branding Sweep

Remove all traces of "Vuexy", "Pixinvent", and "ThemeSelection" branding:

**Files to clean:**

- `package.json`: `"name": "vuexy-vuejs-admin-template"` -- renamed in Phase 0.5
- `index.html`: `localStorage.getItem('vuexy-initial-loader-bg')` and `localStorage.getItem('vuexy-initial-loader-color')` -- rename to `draftnrun-loader-bg` / `draftnrun-loader-color` or remove the dynamic loader color mechanism entirely (use static CSS)
- Dead dialogs referencing "Vuexy", "Pixinvent", `pixinvent.link`, `themeselection-qr.png` -- all deleted in Phase 1.4

**Verification:** After all deletions, run `rg -i "vuexy\|pixinvent\|themeselection" --type-add 'web:*.{vue,ts,js,json,scss,css,html,md}' -t web` to confirm zero remaining references in source code.

### 1.7 Clean Barrel Files

- `src/composables/index.ts`: remove re-exports of deleted files (`useApi`, `useAgents`, `useSkins`)

### 1.8 Remove Unused NPM Packages

```
pnpm remove vue3-apexcharts apexcharts
pnpm remove @fullcalendar/core @fullcalendar/daygrid @fullcalendar/interaction @fullcalendar/list @fullcalendar/timegrid @fullcalendar/vue3
pnpm remove swiper mapbox-gl roboto-fontface vue-prism-component prismjs
pnpm remove vue-shepherd shepherd.js webfontloader msw
pnpm remove vue-i18n @intlify/unplugin-vue-i18n
pnpm remove vue3-perfect-scrollbar @formkit/drag-and-drop
pnpm remove vue-json-viewer vue-flatpickr-component
pnpm remove @sindresorhus/is jwt-decode @floating-ui/dom cookie-es @vueuse/math
pnpm remove @videojs-player/vue video.js shiki
pnpm remove stylelint stylelint-config-idiomatic-order stylelint-config-standard-scss stylelint-use-logical-spec @stylistic/stylelint-config @stylistic/stylelint-plugin
```

Remove after Phase 5g: `pnpm remove tippy.js`

**Validation:** `pnpm build` must succeed after this phase. Zero Vuexy/Pixinvent references in source.

---

## Phase 2 -- Infrastructure Rewrites

### 2a. Auth Store (replace useCookie)

New file: `[src/stores/auth.ts](src/stores/auth.ts)` -- reactive Pinia store replacing all `useCookie` calls.

- State: `userData: Ref<UserData | null>`, `accessToken: Ref<string | null>`, `abilityRules: Ref<AppAbilityRawRule[]>` (all persisted to localStorage)
- Computed: `isAuthenticated`
- Actions: `setAuth(userData, token, rules)` (also calls `Sentry.setUser({ id, email })`), `clearAuth()` (also calls `Sentry.setUser(null)`), `updateAbilities(rules)`

Files to migrate (global find-replace `useCookie('userData')` / `useCookie('accessToken')` / `useCookie('userAbilityRules')`):

- `[src/services/auth.ts](src/services/auth.ts)` (11 useCookie calls)
- `[src/plugins/1.router/guards.ts](src/plugins/1.router/guards.ts)` (5 calls)
- `[src/stores/org.ts](src/stores/org.ts)` (4 calls)
- `[src/utils/abilityRules.ts](src/utils/abilityRules.ts)` (1 call)
- Auth page files: `login.vue`, `register.vue`, `verify-email.vue`, `accept-invite.vue`, `auth/callback` routes

### 2b. CASL Relocation and Cleanup

Move `src/@layouts/plugins/casl.ts` to `src/plugins/casl/navigation.ts`. This file contains `can()`, `canViewNavMenuGroup()`, `canNavigate()` -- critical authorization logic that must not change in behavior.

- Replace `useCookie` calls with auth store reads
- Update all imports from `@layouts/plugins/casl` to `@/plugins/casl/navigation`
- Remove all `console.log` statements from `src/plugins/casl/index.ts` (replace with logger)

### 2c. Theme Config Store

New file: `[src/stores/config.ts](src/stores/config.ts)` (~40 lines). Replaces the bloated `@core/stores/config.ts`.

- State: `theme: 'light' | 'dark' | 'system'`, `isNavCollapsed: boolean` (persisted to localStorage)
- Computed: `resolvedTheme` (handles system preference via `matchMedia`)
- Action: `initTheme()` -- sets Vuetify's active theme via `useTheme().global.name.value`

No cookies, no RTL, no footer type, no skin, no semi-dark nav.

### 2d. Sentry Fix + Logger

**Current state of Sentry is broken.** The init call exists in `main.ts` (line 55) but has critical gaps:

**Fix `Sentry.init()` in `main.ts`:**

- `**tracePropagationTargets`**: Replace placeholder `/^https:\/\/yourserver\.io\/api/` with the actual API domain(s) (the backend URL from `VITE_API_BASE_URL` env var). This enables distributed tracing between frontend and backend.
- **Add `ignoreErrors`**: Filter common noise -- `ResizeObserver loop`, `Non-Error promise rejection`, browser extension errors, `NetworkError when attempting to fetch`.
- **Add `Sentry.setUser()`**: Wire into the auth flow (Phase 2a auth store). Call `Sentry.setUser({ id, email })` on login, `Sentry.setUser(null)` on logout. This goes into the auth store's `setAuth()` and `clearAuth()` actions.
- **Add `Sentry.setContext('organization', { orgId, orgName })`**: Wire into `src/stores/org.ts` when the selected org changes.
- **Guard init**: Wrap in `if (import.meta.env.VITE_SENTRY_DSN)` so it's an explicit no-op when DSN is empty (local dev).
- **Consider `Sentry.replayIntegration()`**: Add Session Replay for reproducing UI bugs (sample rate 0.1 in prod).

**Source maps (critical):**

- Install `@sentry/vite-plugin` (new dependency).
- Add to `vite.config.ts` `plugins` array with `org`, `project`, `authToken` from env vars.
- Add env vars: `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` (not VITE_ prefixed -- build-time only, not client-exposed).
- Enable `build.sourcemap: 'hidden'` in `vite.config.ts` (generates source maps for upload but doesn't expose them in the bundle).
- The plugin auto-uploads source maps on `pnpm build` and deletes them from the output.

**Logger with `Sentry.captureException()`:**

New file: `[src/utils/logger.ts](src/utils/logger.ts)`

```typescript
import * as Sentry from '@sentry/vue'

type LogLevel = 'info' | 'warn' | 'error'

function log(level: LogLevel, message: string, context?: Record<string, unknown>) {
  if (level === 'error') {
    Sentry.captureException(new Error(message), { extra: context })
  } else if (level === 'warn') {
    Sentry.captureMessage(message, { level: 'warning', extra: context })
  }
  Sentry.addBreadcrumb({ category: 'app', message, level, data: context })
  if (import.meta.env.DEV) console[level](`[${level.toUpperCase()}] ${message}`, context ?? '')
}

export const logger = {
  info: (msg: string, ctx?: Record<string, unknown>) => log('info', msg, ctx),
  warn: (msg: string, ctx?: Record<string, unknown>) => log('warn', msg, ctx),
  error: (msg: string, ctx?: Record<string, unknown>) => log('error', msg, ctx),
}
```

Key difference from the previous logger design: `logger.error()` now calls `Sentry.captureException()` (creates a Sentry event), and all levels add breadcrumbs for context trail. This means every caught exception that uses `logger.error()` becomes a Sentry event.

Replace ALL `console.log`/`console.warn`/`console.error` across the codebase (~~100+ occurrences). Key files: `auth.ts`, `guards.ts`, `org.ts`, CASL plugin, `navigation/vertical/others.ts`, `DefaultLayoutWithVerticalNav.vue` (~~15 console.log calls), `main.ts`.

### 2e. i18n Removal

- Delete `src/plugins/i18n/` directory
- Remove `$t()` / `t()` calls (mostly in @core components which are already deleted; scan for any remaining)
- Remove `useI18n()` imports
- Remove `VLocaleProvider` from `App.vue`
- Remove `vue-i18n` from auto-import config in `vite.config.ts`

### 2f. Relocate Shared Utilities

Already extracted in Phase 1.1. Verify relocated files compile and all imports point to new locations:

- `src/utils/colorConverter.ts` (used in `App.vue` for hex-to-rgb)
- `src/utils/chartConfig.ts` (used by monitoring chart components)
- Any merged validator/formatter/helper utilities

### 2g. Split scopeoApi into Domain Modules

Split `[src/services/scopeoApi.ts](src/services/scopeoApi.ts)` (1,088 lines, 22 API modules) into:

```
src/api/
  index.ts          -- barrel re-export + backward-compatible scopeoApi aggregate
  workflows.ts      -- projectsApi (renamed to workflowsApi), templatesApi
  agents.ts         -- agentsApi
  studio.ts         -- studioApi
  observability.ts  -- observabilityApi
  qa.ts             -- qaApi, qaEvaluationApi
  knowledge.ts      -- knowledgeApi
  cron.ts           -- cronApi
  organization.ts   -- organizationSecretsApi, organizationLimitsApi, organizationCreditUsageApi, orgVariableDefinitionsApi, variableSetsApi
  widgets.ts        -- widgetApi
  integration.ts    -- integrationApi
  auth-keys.ts      -- apiKeysApi, orgApiKeysApi
  files.ts          -- filesApi
  llm-models.ts     -- llmModelsApi
  admin.ts          -- adminToolsApi, settingsSecretsApi, componentsApi, categoriesApi
  chat.ts           -- chatApi, runsApi
  oauth.ts          -- oauthConnectionsApi
  sources.ts        -- sourcesApi, ingestionTaskApi
```

The `$api` base client stays in `[src/utils/api.ts](src/utils/api.ts)`. The barrel provides a `scopeoApi` aggregate object for backward compatibility during migration. Consumers gradually switch from `scopeoApi.projects.getAll()` to `import { workflowsApi } from '@/api/workflows'`.

### 2h. Icon System

Rebuild `[src/plugins/icons.ts](src/plugins/icons.ts)` using `@iconify/vue` with lazy-loading. Keep icon JSON packages: `@iconify-json/tabler`, `@iconify-json/mdi`, `@iconify-json/ph`, `@iconify-json/fa`, `@iconify-json/logos`. Integrate with Vuetify's icon system via `createVuetify({ icons })` config.

### 2i. Data Fetching Architecture Cleanup

The codebase has 19 TanStack Query composables but ~12 components bypass them with direct `scopeoApi` calls, causing duplicate fetches, no caching, and inconsistent loading states. This phase establishes conventions and fixes the worst offenders. These conventions also prepare for a future WebSocket layer: when all data flows through TanStack Query, real-time updates from WebSockets just call `queryClient.invalidateQueries()` or `queryClient.setQueryData()` with zero component changes.

**Conventions to enforce (documented in cursor rules Phase 8):**

- **All data reads go through TanStack Query composables.** No direct `scopeoApi.*.get*()` calls in components/pages. If a composable doesn't exist, create one.
- **Mutations use `useMutation` hooks**, not inline `scopeoApi` calls. Mutations invalidate related query caches on success.
- **Standard query defaults:** `staleTime: 5 * 60 * 1000` (5min), `gcTime: 30 * 60 * 1000` (30min), `refetchOnMount: true`, `refetchOnWindowFocus: false`. Override per-query only when needed (e.g., observability polling at 10s, knowledge files at 30s).
- **Loading states:** Pages use skeleton loaders (Phase 5-pre). Components use the `isLoading` / `isPending` from TanStack, never manual `ref(true/false)`.
- **Error states:** Use `ErrorState.vue` component (Phase 5-pre) with the `error` ref from TanStack.
- **Prefetching:** Add `queryClient.prefetchQuery()` on list page item hover for detail pages (agents, workflows). This warms the cache so detail pages load instantly when clicked.
- **Acceptable exceptions:** Streaming chat (`chatApi.chat()`), file uploads, CSV export/import, autocomplete suggestions -- these are one-off actions, not cached data.

**Critical fixes (during Phase 5 component migration):**

1. `**agents/[id].vue`**: Replace manual `getAgentById()` + `ref<Agent>` + `isAgentLoading` with `useAgentQuery(agentId)`. The composable already exists and is unused on this page.
2. `**StudioFlow.vue`**: Create new `useGraphQuery(projectId, graphRunnerId)` composable wrapping `scopeoApi.studio.getGraph()`. This is the most complex data fetch in the app and currently has zero caching.
3. `**SharedPlayground.vue`**: Replace direct `scopeoApi.agents.getAll()` / `getById()` calls with existing `useAgentsQuery` / `useAgentQuery`.
4. `**RunHistoryDrawer.vue`**: Replace direct `scopeoApi.observability.`* calls with existing `useTraceListQuery` / `useTraceDetailsQuery`.
5. `**EditSidebar.vue`**: Replace direct `scopeoApi.sources.getAll()` with existing `useSourcesQuery`.
6. `**ApiKeys.vue` / `SharedAPI.vue`**: Create `useApiKeysQuery` composable, consolidate duplicate code into a shared hook.
7. `**AgentSaveDeployButtons.vue`**: Use existing `useDeployAgentMutation` instead of inline `scopeoApi.agents.deploy()`.
8. **List pages**: Add `queryClient.prefetchQuery()` on item hover/mouseenter for detail page data (agent or workflow by ID).

**New query composables to create:**

- `useGraphQuery(projectId, graphRunnerId)` -- for `StudioFlow.vue` graph loading
- `useApiKeysQuery(orgId)` + `useCreateApiKeyMutation` + `useRevokeApiKeyMutation` -- for API key management
- `useOrganizationSecretsQuery(orgId)` + mutations -- for organization settings secrets tab

**Validation:** `pnpm build` must succeed after this phase.

---

## Phase 3 -- Wrapper Component Unwrap

The @core wrapper components (`AppTextField`, `AppSelect`, `AppAutocomplete`, `AppCombobox`, `AppTextarea`) add an external `VLabel` above the input instead of using Vuetify's built-in floating label. They also add wrapper divs and custom IDs. After Phase 1 deletes dead dialogs, only ~10 live files use these wrappers.

**Decision:** Replace all wrapper usages with plain Vuetify components using standard floating labels. The external above-input label is a Vuexy design choice, not a product requirement. The Vuetify global defaults in `defaults.ts` already configure `variant: 'outlined'`, `density: 'comfortable'`, `color: 'primary'`, `hideDetails: 'auto'` for all form components, so plain Vuetify components will look consistent without extra configuration.

### 3.1 Replace Wrapper Usages in Live Files

- `src/pages/login.vue`, `register.vue`, `forgot-password.vue`, `reset-password.vue` -- `AppTextField` to `VTextField`
- `src/pages/org/[orgId]/data-sources.vue` -- `AppTextField`, `AppSelect` to `VTextField`, `VSelect`
- `src/components/AppSearchHeader.vue` -- `AppTextField` to `VTextField`
- `src/components/knowledge/KnowledgeFileSidebar.vue` -- `AppTextField` to `VTextField`

### 3.2 Clean Up defaults.ts

Remove `app-autocomplete__content`, `app-inner-list`, `app-select__content` CSS class references from VAutocomplete/VSelect/VCombobox `menuProps` in `[defaults.ts](src/plugins/vuetify/defaults.ts)`.

---

## Phase 4 -- Layout System Rebuild

### 4.1 App Shell with Vuetify Layout Components

Rebuild `[src/layouts/default.vue](src/layouts/default.vue)` using Vuetify's native layout:

```
VApp
  AppSidebar (VNavigationDrawer, left)
  VMain
    RouterView (page content -- full width)
```

No global top bar. Org selector, theme toggle, user profile live in the sidebar.

### 4.2 Sidebar Component

New: `**AppSidebar.vue**` -- uses `VNavigationDrawer` with `rail` prop for collapse/expand. Structure:

- **Header**: Logo / collapsed icon
- **Nav items**: `VList` / `VListItem` with CASL `can()` visibility. Items: Agents, Workflows, Scheduler, Knowledge, Variables, Integrations, Monitoring, Settings (admin-only), Super Admin (super-admin-only). Flat list (no grouped sections).
- **Footer**: Org selector dropdown, theme toggle, user avatar + menu (profile, logout), docs link, Discord link

Supporting components: `AppSidebarItem.vue`, `AppSidebarGroup.vue` (collapsible group via `VListGroup`).

### 4.3 Navigation Config Rewrite

Rewrite `[src/navigation/vertical/others.ts](src/navigation/vertical/others.ts)` as a proper composable (`useNavItems`). Current issues:

- Async function that returns a Ref with watchers created inside (memory leak risk if called multiple times)
- `console.log` spam (~15 statements)
- Super Admin item is added then immediately filtered out in the layout component

New pattern: a `useNavItems()` composable that returns a computed list of nav items based on reactive dependencies (org role, projects, agents, super admin status). CASL filtering happens inside the composable, not in the layout.

### 4.4 Entity Header Bar

For workflow/agent detail pages -- rendered inside the page, not as a global element:

```
Breadcrumb:  Workflows > My Workflow Name
[icon] [edit name] [version badge] [playground btn] [observability btn] [run history btn]
[Studio]  [QA]  [Integration]                                        <-- VTabs
```

Content below tabs fills full width. No empty space on the right when panels are closed.

### 4.5 Floating Panels (Playground + Run History)

Decouple playground and observability into separate components (currently tightly coupled in `RunHistoryFloatingPanel.vue`), but **reproduce the exact same visibility behavior**:

**Visibility logic (unchanged):**

- **Studio tab**: Playground is always visible (no close/collapse). Run history/observability is accessible via toggle ("Inspect runs" drawer).
- **QA tab**: No panels (component unmounted).
- **Integration tab**: No panels (component unmounted).
- This is controlled by a `v-if` at the page level: `activeTab !== 'integration' && activeTab !== 'qa'`.

**Implementation changes:**

- **Split `RunHistoryFloatingPanel.vue`** into two independent components: `PlaygroundPanel.vue` (wraps the playground component) and `ObservabilityDrawer.vue` (wraps `UniversalObservabilityDrawer`). Currently both live in a single 525-line component with shared resize logic.
- **Remove `WorkflowFloatingActions.vue` and `AgentFloatingActions.vue`** thin wrappers -- the panels are mounted directly in the shared `EntityDetailPage.vue` (Phase 5c).
- **Simplify resize**: replace manual mousedown/mousemove/mouseup resize handlers with either Vuetify drawer or CSS `resize` property.
- Main content area shrinks to accommodate the playground panel when visible (same as today via `availableSpace` computed).

### 4.6 Unified Toast/Notification System

**Current state:** 18 files each manage their own `VSnackbar` with local `showSnackbar` / `snackbarMessage` / `snackbarColor` state (~50 lines of boilerplate per file). `App.vue` has a separate `sessionStorage` hack for access-denied messages.

Create:

- `**useNotifications()` composable** -- exposes `notify.success(msg)`, `notify.error(msg)`, `notify.warning(msg)`, `notify.info(msg)`. Internally pushes to a shared reactive queue.
- `**AppNotifications.vue`** -- single global component mounted in `App.vue`. Renders queued notifications as `VSnackbar` with consistent positioning (bottom-right), auto-dismiss (3s for success, 5s for errors), and stacking.

Migrate all 18 files to use `useNotifications()` instead of local snackbar state. Delete the `sessionStorage` access-denied hack.

### 4.7 App.vue Simplification

- Remove `VLocaleProvider` (i18n gone)
- Keep `VApp` (Vuetify requires it as root)
- Init theme store on mount
- Mount `AppNotifications.vue` globally

### 4.8 Blank Layout

Rebuild `[src/layouts/blank.vue](src/layouts/blank.vue)` -- minimal wrapper for auth and public pages. Centered content area, no sidebar.

### 4.9 Layout Component Cleanup

- Rebuild: `OrgSelector.vue`, `UserProfile.vue`, `NavbarThemeSwitcher.vue`, `Footer.vue` (remove @core/@layouts deps, use native CSS scrollbars instead of perfect-scrollbar)
- Delete: `NavSearchBar.vue`, `NavbarShortcuts.vue`, `NavBarNotifications.vue`, `DefaultLayoutWithVerticalNav.vue`, `DefaultLayoutWithHorizontalNav.vue`

**Validation:** App loads, sidebar navigation works, org selector works, theme toggle works.

---

## Phase 5 -- Page and Component Migration

### Shared UI Patterns (build first, use during migration)

**Reusable skeleton templates** (currently only 3 pages use skeletons, most show a spinner or nothing):

- `ListPageSkeleton.vue` -- card grid or list with shimmer placeholders
- `DetailPageSkeleton.vue` -- header + tab area + content area shimmer
- `TableSkeleton.vue` -- table rows with shimmer cells

**Shared state components** (currently empty/error states are ad-hoc per page):

- `EmptyState.vue` -- icon + title + description + optional action button
- `ErrorState.vue` -- error icon + message + retry button

### Migration checklist per file

1. Remove `@core/` and `@layouts/` imports
2. Replace `@core/scss/`* style imports with new minimal CSS (auth.scss / misc.scss)
3. Remove `console.log` statements (use logger)
4. Adapt to new layout structure (entity header, panel toggles)
5. Replace local `VSnackbar` state with `useNotifications()`
6. **Replace direct `scopeoApi` data reads with TanStack Query composables** (see Phase 2i critical fixes)
7. **Replace manual `isLoading` refs with TanStack's `isLoading`/`isPending`**
8. Add skeleton loading states where missing
9. Use `EmptyState` / `ErrorState` components where applicable

### 5a. Auth Pages (6 pages)

`login.vue`, `register.vue`, `forgot-password.vue`, `reset-password.vue`, `verify-email.vue`, `accept-invite.vue`

- Replace `AppTextField` with `VTextField`
- Remove `@core/scss/template/pages/page-auth` imports (already cleaned in Phase 1.5), use new `auth.scss`
- Remove `useGenerateImageVariant` and `VNodeRenderer` (from @core/@layouts)
- **Remove hardcoded test credentials** in `login.vue` (`signupTestUser` function with real email/password) -- security concern

### 5b. Core Pages

- `**index.vue`** (homepage), `**home.vue`**: remove @core imports
- **Workflow list** (`projects/index.vue`) and **Agent list** (`agents/index.vue`): extract duplicated edit dialog into a shared `EditEntityDialog.vue` component (currently only label text differs between the two)

### 5c. Entity Detail Pages -- Deduplication

`**projects/[id].vue`** (workflow detail) and `**agents/[id].vue`** (agent detail) share ~80% of their code: entity header, tabs, skeleton loaders, icon editor, version selector, floating panel integration, modals. This is the single biggest duplication in the codebase.

Extract a shared `**EntityDetailPage.vue`** component with:

- Props: `entityType` ('workflow' | 'agent'), `entityId`, `tabs` config
- Slots: per-tab content (Studio, QA, Integration)
- Shared logic: entity header rendering, tab management, `availableSpace` computed, panel toggle integration
- Entity-specific logic stays in the page files via slots/props

Also fix:

- Remove empty `Promise.all([])` dead code in `projects/[id].vue`
- Remove redundant `v-if` inside `VWindowItem` (VWindow handles lazy rendering)
- Simplify deeply nested ternary chains in `agents/[id].vue` (lines 328-340, 382-393)

Data fetching fixes (Phase 2i):

- `**agents/[id].vue`**: Remove manual `getAgentById()` + `ref<Agent>` + `isAgentLoading`. Use `useAgentQuery(agentId)` instead -- the composable exists but is currently unused on this page. Eliminates double-fetch on mount.
- **Both detail pages**: Add `queryClient.prefetchQuery()` calls in list pages on row hover/mouseenter, so detail data is warm when the user clicks through.

### 5d. Domain Pages

- `data-sources.vue`, `monitoring.vue`, `scheduler/index.vue`, `variables.vue`, `connections.vue`, `organization.vue`, `super-admin.vue`
- Remove @core/@layouts references. Keep `VDataTable`.
- `**organization.vue`**: Create `useOrganizationSecretsQuery(orgId)` + mutations -- currently fetched once in `onMounted`, never refreshed, no caching.

### 5e. Static Pages

- `privacy-policy.vue`, `terms-conditions.vue`: replace `@core/scss` imports, keep markdown rendering
- `not-authorized.vue`, `[...error].vue`: replace `misc.scss` import (already cleaned in Phase 1.5)
- `admin/whitelist.vue`: remove @core refs

### 5f. Component Decomposition

**EditSidebar.vue** (3,365 lines) into 8 sub-components:

- `ParameterRenderer.vue` -- single parameter widget (eliminates ~600 lines of duplication)
- `ParameterGroupCard.vue` -- collapsible group with header toggle
- `PortMappingSection.vue` -- input/output port select UI
- `ToolDescriptionEditor.vue` -- right-column tool description form
- `OptionalToolsList.vue` -- optional subcomponent toggles
- `GmailIntegrationSection.vue` -- Gmail OAuth card
- `EditSidebarHeader.vue` -- dialog header
- `EditSidebarFooter.vue` -- footer with metadata + buttons

**SharedPlayground.vue** (3,151 lines) into 6 sub-components:

- `PlaygroundChatInput.vue` -- textarea + send button + file attach
- `PlaygroundFileAttachments.vue` -- file chip display, drag-and-drop
- `PlaygroundCustomFields.vue` -- dynamic JSON/simple/file fields
- `PlaygroundVariableSetSelector.vue` -- variable set multi-select
- `PlaygroundWelcomeState.vue` -- empty conversation UI
- Remove ~773 lines of dead CSS (commented-out chat-history styles)
- **Data fetching fix**: Replace direct `scopeoApi.agents.getAll()` / `getById()` calls with existing `useAgentsQuery` / `useAgentQuery` composables

**QADatasetTable.vue** (2,507 lines) into 2 composables + 3 sub-components:

- `useQARunOrchestration.ts` -- sync/async run logic, WebSocket
- `useQATestCaseState.ts` -- local testCases state, CRUD, lastSaved
- `QAGroundtruthCell.vue` -- inline-editable groundtruth cell
- `QACustomColumnCell.vue` -- inline-editable custom column cell
- `QAProgressBanner.vue` -- async run progress bar

**StudioFlow.vue** (2,009 lines) into 3 composables + 1 sub-component:

- `useStudioGraphPersistence.ts` -- save, auto-save, deploy (~200 lines)
- `useStudioNodeCrud.ts` -- create, delete, edit nodes (~300 lines)
- `useStudioNavigation.ts` -- zoom, breadcrumbs, active component tracking (~200 lines)
- `StudioToolbar.vue` -- breadcrumbs + action buttons
- **Data fetching fix**: Create `useGraphQuery(projectId, graphRunnerId)` composable wrapping `scopeoApi.studio.getGraph()` -- this is the most complex data fetch in the app and currently has zero caching. This also prepares for future WebSocket-driven graph updates (just `queryClient.setQueryData()`).

**Organization settings** (`organization.vue`, 1,100+ lines) into tab-specific components:

- `OrgGeneralTab.vue` -- general settings form
- `OrgMembersTab.vue` -- member list + invite
- `OrgSecretsTab.vue` -- secrets management
- `OrgApiKeysTab.vue` -- API key management

### 5g. tippy.js Migration

Two live files use `tippy.js`: `[FieldExpressionInput.vue](src/components/studio/inputs/FieldExpressionInput.vue)` and `[KnowledgeEditor.vue](src/components/knowledge/KnowledgeEditor.vue)`. Replace with Vuetify's `VTooltip` or `VMenu` depending on the interaction pattern. Then `pnpm remove tippy.js`.

### 5h. Chart.js Wrappers and Shared Components

- Relocate 7 chart wrapper components (already extracted in Phase 1.1 to `src/components/charts/`)
- Update `chartConfig.ts` to read theme colors from Vuetify's theme instead of @core utilities
- Rebuild `GenericConfirmDialog.vue` (used in 13+ components) -- remove @core dependencies
- Rebuild `HelpRequestDialog.vue` -- remove @core dependencies
- Rebuild `GlobalHelpButton.vue`
- Restyle `MDContent.vue` -- keep `markdown-it`, remove @core styling

---

## Phase 6 -- Final Cleanup

### 6.1 Remove Migration Scaffolding

- Remove `@core` and `@layouts` path aliases from `vite.config.ts` (zero imports should remain)
- Remove `@themeConfig` alias
- Remove `unplugin-vue-define-options` if present (Vue 3.5 has native `defineOptions`)
- Remove `destr`, `ufo` packages if no longer imported after `useCookie` removal

### 6.2 Dead File Cleanup

- Delete `src/assets/styles/styles.scss` (empty file, if not already deleted in Phase 1.5)
- Delete `src/assets/styles/variables/_template.scss` and `_vuetify.scss` (if not already deleted in Phase 1.5)
- Clean up `auto-imports.d.ts` and `components.d.ts` (auto-generated, remove from git if tracked)

### 6.3 Final Branding Verification

Run `rg -i "vuexy\|pixinvent\|themeselection" --type-add 'web:*.{vue,ts,js,json,scss,css,html}' -t web` and confirm **zero** results in source code. Check `index.html`, `package.json`, and any config files.

### 6.4 Build Verification

- `pnpm build` -- fix any remaining errors
- `pnpm lint` -- fix issues

---

## Phase 7 -- Testing

Full coverage for new code, smoke tests for migrated pages:

- **Auth flow**: login, logout, session recovery, route guards, ability rules persistence
- **Navigation**: sidebar rendering based on CASL permissions, org switching, nav collapse
- **Theme**: dark/light toggle persists across sessions, Vuetify theme updates correctly
- **API modules**: barrel exports match old `scopeoApi` interface (no broken imports)
- **Auth store**: `setAuth`, `clearAuth`, `updateAbilities`, localStorage persistence
- **Config store**: theme persistence, nav collapse persistence
- **Toast system**: `useNotifications` composable, global rendering, auto-dismiss
- **Extracted composables**: `useStudioGraphPersistence`, `useStudioNodeCrud`, `useStudioNavigation`, `useQARunOrchestration`, `useQATestCaseState`, `useNavItems`
- **Sentry integration**: verify `Sentry.init()` runs with correct config, `setUser` called on login/logout, `setContext` on org switch, logger.error triggers `captureException`, source maps upload in build
- **Smoke tests**: login page, sidebar navigation, open a workflow, open an agent, monitoring charts, organization settings, data sources

---

## Phase 8 -- Documentation and Cursor Rules

### README.md

Complete rewrite of `[README.md](README.md)`:

- Project overview (Draft'n Run frontend -- Vue 3 + Vuetify SaaS back-office)
- Tech stack with versions
- Project structure with directory tree
- Getting started (prerequisites, env setup, dev server, build)
- Architecture decisions (auth flow, API layer, state management, CASL permissions)
- Deployment (Netlify + Docker)

### Cursor Rules

`**back-office-architecture.mdc`:**

- Directory structure map
- Component naming conventions
- Composable patterns (`composables/queries/` for TanStack Query hooks)
- API module pattern (one file per domain in `src/api/`)
- State management (auth store, org store, config store -- no other global stores)
- "Workflow" vs "Project" naming convention

`**back-office-styling.mdc`:**

- Use Vuetify components and theming system
- Design tokens via Vuetify theme config, not custom CSS variables
- Max component size: 400 lines -- extract sub-components or composables beyond that
- No `!important` overrides on Vuetify internals

`**back-office-practices.mdc`:**

- ALWAYS update README and cursor rules when adding/removing screens, routes, components, or patterns
- Use `logger.`* instead of `console.`*
- **Data fetching rules:**
  - All data reads MUST go through TanStack Query composables in `src/composables/queries/`. No direct `scopeoApi.*.get*()` calls in components/pages.
  - Mutations use `useMutation` hooks, not inline `scopeoApi` calls. Mutations invalidate related query caches on success.
  - Standard query defaults: `staleTime: 5min`, `gcTime: 30min`, `refetchOnMount: true`, `refetchOnWindowFocus: false`. Override only with justification.
  - Loading states come from TanStack (`isLoading` / `isPending`), never manual `ref(true/false)`.
  - Add `queryClient.prefetchQuery()` on list page hover for detail pages.
  - Acceptable exceptions: streaming chat, file uploads, CSV export/import, autocomplete.
  - Future WebSocket updates will use `queryClient.invalidateQueries()` / `setQueryData()` -- this is why all data must flow through TanStack.
- Use `useNotifications()` for toast messages, never local VSnackbar state
- Error handling: never bare `catch {}`, always log to Sentry
- No dead code: remove unused imports, components, commented-out blocks in every PR
- Test new components and composables

---

## File Change Summary

- **Files deleted:** ~240 (139 @core + 29 @layouts + 36 fake-api + 15 dialogs + 15 misc dead files + 3 SCSS + 1 stylelintrc)
- **Files created:** ~45 (stores, utils, API modules, layout components, shared UI patterns, extracted sub-components, toast system, auth/misc CSS, docs, cursor rules)
- **Files modified:** ~50-60 (pages with @core imports, layout files, main.ts, vite.config, plugins, index.html, large components being decomposed)
- **NPM packages removed:** ~34 (28 libraries + 6 stylelint)
- **NPM packages added:** 2 (@fontsource/inter, @sentry/vite-plugin)
- **Net LOC change:** estimated -15,000 to -18,000 lines removed

## Validation Commands (after each phase)

- `pnpm build` -- zero errors
- `pnpm lint` -- must pass
- `pnpm test` -- must pass
- `rg -i "vuexy\|pixinvent\|themeselection"` -- zero results in source
- Manual smoke test: login, sidebar nav, open workflow, open agent, check monitoring charts, org settings

