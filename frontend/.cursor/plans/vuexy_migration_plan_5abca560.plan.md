---
name: Vuexy Migration Plan
overview: Complete removal of all Vuexy/Vuetify proprietary code (3,167 component instances, 139 @core files, 29 @layouts files) and replacement with Tailwind CSS, custom base components, a new minimalist design system, rebuilt layout/navigation, decomposed large components, split API modules, new auth store, full test coverage, and comprehensive documentation.
todos:
  - id: phase-0-tailwind
    content: "Phase 0: Install Tailwind, create design tokens, update vite.config.ts, rename package.json"
    status: pending
  - id: phase-1-purge
    content: "Phase 1: Delete all dead code -- @core/, @layouts/, fake-api/, 16 unused dialogs, MagicalWorkflowBuilder, customer page, ~30 npm packages"
    status: pending
  - id: phase-2-auth
    content: "Phase 2a: Build auth store (Pinia + localStorage), replace all useCookie calls across auth.ts, guards.ts, org.ts, abilityRules.ts, pages"
    status: pending
  - id: phase-2-casl
    content: "Phase 2b: Relocate CASL navigation helpers from @layouts to src/plugins/casl/, clean up console.logs"
    status: pending
  - id: phase-2-config
    content: "Phase 2c: Build slim theme config store (~40 lines), replace @core/stores/config.ts"
    status: pending
  - id: phase-2-logger
    content: "Phase 2d: Create logger.ts, replace all console.log/warn/error (~100+ occurrences)"
    status: pending
  - id: phase-2-moment
    content: "Phase 2e: Migrate 21 files from moment to date-fns, remove moment"
    status: pending
  - id: phase-2-i18n
    content: "Phase 2f: Remove i18n -- delete plugin, replace $t() calls, remove VLocaleProvider"
    status: pending
  - id: phase-2-utils
    content: "Phase 2g: Relocate useful @core utilities to src/utils/"
    status: pending
  - id: phase-2-api
    content: "Phase 2h: Split scopeoApi.ts into 16 domain modules in src/api/"
    status: pending
  - id: phase-2-icons
    content: "Phase 2i: Set up icon system with @iconify/vue wrapper"
    status: pending
  - id: phase-3-critical
    content: "Phase 3a: Build 4 critical UI components (UiButton, UiIcon, UiCard, UiDivider) -- covers 47% of instances"
    status: pending
  - id: phase-3-high
    content: "Phase 3b: Build 7 high-priority UI components (UiInput, UiTextarea, UiSelect, UiChip, UiAlert, UiDialog, UiTooltip)"
    status: pending
  - id: phase-3-medium
    content: "Phase 3c: Build 14 medium-priority UI components (UiAvatar, UiCheckbox, UiSwitch, UiRadio, UiTabs, UiMenu, UiList, UiProgress, UiSnackbar, UiSkeleton, UiForm, UiBadge)"
    status: pending
  - id: phase-3-table
    content: "Phase 3d: Build UiDataTable with TanStack Vue Table"
    status: pending
  - id: phase-3-cmdpalette
    content: "Phase 3e: Build CommandPalette component (Cmd+K)"
    status: pending
  - id: phase-4-layout
    content: "Phase 4: Rebuild layout system -- AppSidebar, AppTopbar, default.vue, blank.vue, App.vue rewrite"
    status: pending
  - id: phase-5-auth-pages
    content: "Phase 5a: Migrate 6 auth pages (login, register, forgot-password, reset-password, verify-email, accept-invite)"
    status: pending
  - id: phase-5-core-pages
    content: "Phase 5b: Migrate 6 core pages (index, home, projects list/detail, agents list/detail)"
    status: pending
  - id: phase-5-domain-pages
    content: "Phase 5c: Migrate 7 domain pages (data-sources, monitoring, scheduler, variables, connections, organization, super-admin)"
    status: pending
  - id: phase-5-static-pages
    content: "Phase 5d: Migrate 5 static pages (privacy, terms, error, not-authorized, whitelist)"
    status: pending
  - id: phase-5-decompose
    content: "Phase 5e: Decompose large components -- EditSidebar (8 sub), SharedPlayground (6 sub), QADatasetTable (6 extractions), StudioFlow (4 composables)"
    status: pending
  - id: phase-5-components
    content: "Phase 5f: Migrate all remaining business components (~100 files), chart wrappers, shared components"
    status: pending
  - id: phase-6-cleanup
    content: "Phase 6: Final cleanup -- remove aliases, bundle analysis, delete dead CSS, remove stylelint"
    status: pending
  - id: phase-7-tests
    content: "Phase 7: Write tests -- UI component tests, integration tests, composable tests"
    status: pending
  - id: phase-8-docs
    content: "Phase 8: Rewrite README, cursor rules (architecture, styling, practices), design system docs"
    status: pending
isProject: false
---

# Vuexy/Vuetify Removal and Tailwind Migration

## Current State Snapshot

- **3,167 Vuetify component instances** across 185 files (62 unique component types)
- **139 files** in `src/@core/` (Vuexy template core)
- **29 files** in `src/@layouts/` (Vuexy layout system)
- **36+ dead files** in `src/plugins/fake-api/`
- **16 dead dialog components**, **19 dead @core components**
- **~25 unused npm packages** to remove
- **4 giant components** to decompose (3,365 / 3,151 / 2,507 / 2,009 lines)
- **1,088-line monolith API** to split into domain modules
- Cookie-based auth to replace with Pinia store + localStorage

## Dependency Audit Summary

**REMOVE (confirmed unused):**
`vuetify`, `vite-plugin-vuetify`, `vue3-apexcharts`, `apexcharts`, `@fullcalendar/`* (6 packages), `swiper`, `mapbox-gl`, `roboto-fontface`, `vue-prism-component`, `prismjs`, `vue-shepherd`, `shepherd.js`, `webfontloader`, `msw`, `vue-i18n`, `@intlify/unplugin-vue-i18n`, `moment`, `vue3-perfect-scrollbar`, `@formkit/drag-and-drop`, `vue-json-viewer`, `vue-flatpickr-component`, `@sindresorhus/is`, `jwt-decode`, `@videojs-player/vue`, `video.js`, `shiki`, `@vueuse/math` (audit first), `tippy.js` (replace), `@floating-ui/dom`, `cookie-es`

**KEEP:** `vue`, `vue-router`, `pinia`, `@vueuse/core`, `@tanstack/vue-query`, `@supabase/supabase-js`, `@sentry/vue`, `@casl/ability`, `@casl/vue`, `chart.js`, `vue-chartjs`, `@vue-flow/`*, `@tiptap/`*, `highlight.js`, `markdown-it`, `date-fns`, `ofetch`, `uuid`, `gpt-tokenizer`, `cronstrue`, `lodash-es`, `@iconify/vue`, `@iconify-json/*`, `dagre`, `@codemirror/*`

**ADD:** `tailwindcss`, `@tailwindcss/forms`, `@tailwindcss/typography`, `postcss`, `autoprefixer`, `@tanstack/vue-table`, `@fontsource/inter`

---

## Phase 0 -- Foundation (Tailwind + Design Tokens)

### 0.1 Install and Configure Tailwind CSS

- `pnpm add -D tailwindcss @tailwindcss/forms @tailwindcss/typography postcss autoprefixer`
- `pnpm add @fontsource/inter`
- Create `tailwind.config.ts` with custom theme:
  - Primary: `#22577A` (kept), hover: `#2B6D99`
  - Secondary: `#38A3A5` (kept)
  - Surfaces: light `#FAFBFC`, dark `#0F1117`
  - Inter font family
  - Glass effect utilities (`backdrop-blur`, semi-transparent backgrounds)
  - Border radius: `rounded-lg` (8px) for cards, `rounded-md` for inputs
  - Shadows: subtle layered (`shadow-sm`, `shadow-md`, custom `shadow-glass`)
- Create `postcss.config.js`
- Create [src/assets/styles/tokens.css](src/assets/styles/tokens.css) with CSS custom properties for light/dark themes, toggled via `data-theme="dark"` on `<html>`

```css
:root {
  --color-primary: 34 87 122;
  --color-secondary: 56 163 165;
  --color-surface: 250 251 252;
  --color-surface-elevated: 255 255 255;
  --color-text: 15 17 23;
  --color-text-muted: 107 114 128;
  --color-border: 229 231 235;
  --color-danger: 239 68 68;
  --color-warning: 245 158 11;
  --color-success: 34 197 94;
  --glass-bg: rgba(255,255,255,0.72);
  --glass-blur: 16px;
  --glass-border: rgba(255,255,255,0.18);
}
[data-theme="dark"] {
  --color-surface: 15 17 23;
  --color-surface-elevated: 24 27 35;
  --color-text: 243 244 246;
  --color-text-muted: 156 163 175;
  --color-border: 55 65 81;
  --glass-bg: rgba(15,17,23,0.72);
  --glass-border: rgba(255,255,255,0.08);
}
```

Wire into `tailwind.config.ts` via `theme.extend.colors` using `rgb(var(--color-X) / <alpha-value>)`.

### 0.2 Update Vite Config

In [vite.config.ts](vite.config.ts):

- Remove `vite-plugin-vuetify` plugin + import
- Remove `vuetify` from `optimizeDeps.exclude`
- Remove `@configured-variables`, `@db`, `@api-utils` aliases
- Update `unplugin-vue-components` dirs: remove `src/@core/components`, keep `src/components`
- Update `unplugin-auto-import` dirs: remove all `@core` paths, keep `src/composables/**`, `src/utils/**`
- Remove `@intlify/unplugin-vue-i18n` plugin
- Keep aliases `@core` and `@layouts` temporarily during migration (remove in Phase 6)
- Add PostCSS config for Tailwind

### 0.3 Rename package.json

- `"name": "draftnrun-frontend"`
- `"version": "1.0.0"`

---

## Phase 1 -- Dead Code Purge

Delete everything confirmed unused before touching live code.

### 1.1 Delete Entire Directories

- `src/@core/` (139 files) -- Vuexy proprietary core
- `src/@layouts/` (29 files) -- Vuexy layout system
- `src/plugins/fake-api/` (36 files) -- Vuexy demo mock data
- `src/plugins/vuetify/` (4 files) -- Vuetify plugin
- `src/plugins/i18n/` -- i18n plugin + locale files
- `src/plugins/iconify/` -- will be rebuilt
- `src/views/` (1 file) -- AuthProvider.vue, unused
- `src/navigation/horizontal/` -- unused horizontal nav config

### 1.2 Delete Unused Files

- `src/plugins/webfontloader.ts` -- replaced with CSS @import
- `src/plugins/layouts.ts` -- Vuexy layout plugin wrapper
- `src/composables/useApi.ts` -- deprecated legacy fetch wrapper (not imported anywhere)
- `src/composables/useAgents.ts` -- deprecated, replaced by TanStack Query hooks
- `themeConfig.ts` -- Vuexy theme config
- `src/styles/theme-example.scss` -- unused
- `src/utils/paginationMeta.ts` -- only used in dead code
- `src/utils/fileUtils.ts` -- audit: only if MSW-related

### 1.3 Delete Dead Components

16 unused dialog components:

- `AddAuthenticatorAppDialog.vue`, `AddEditAddressDialog.vue`, `AddEditPermissionDialog.vue`, `AddEditRoleDialog.vue`, `AddPaymentMethodDialog.vue`, `CardAddEditDialog.vue`, `ConfirmDialog.vue`, `CreateAppDialog.vue`, `EnableOneTimePasswordDialog.vue`, `PaymentProvidersDialog.vue`, `PricingPlanDialog.vue`, `ReferAndEarnDialog.vue`, `ShareProjectDialog.vue`, `TwoFactorAuthDialog.vue`, `UserInfoEditDialog.vue`, `UserUpgradePlanDialog.vue`

Dead app components:

- `src/components/AppPricing.vue` -- unused
- `src/components/MagicalWorkflowBuilder.vue` (2,490 lines) -- dead code
- `src/pages/try-builder.vue` -- only consumer of MagicalWorkflowBuilder
- `src/pages/builder-minimal.vue` -- only consumer of MagicalWorkflowBuilder
- `src/pages/customer/index.vue` -- mock demo page
- `src/pages/access-control.vue` -- Vuexy demo

### 1.4 Clean composables/index.ts Barrel

Remove re-exports of deleted files (`useApi`, `useAgents`, `useSkins`).

### 1.5 Remove Unused NPM Packages

```
pnpm remove vuetify vite-plugin-vuetify vue3-apexcharts apexcharts
pnpm remove @fullcalendar/core @fullcalendar/daygrid @fullcalendar/interaction @fullcalendar/list @fullcalendar/timegrid @fullcalendar/vue3
pnpm remove swiper mapbox-gl roboto-fontface vue-prism-component prismjs
pnpm remove vue-shepherd shepherd.js webfontloader msw
pnpm remove vue-i18n @intlify/unplugin-vue-i18n
pnpm remove vue3-perfect-scrollbar @formkit/drag-and-drop
pnpm remove vue-json-viewer vue-flatpickr-component
pnpm remove @sindresorhus/is jwt-decode @floating-ui/dom cookie-es
pnpm remove @videojs-player/vue video.js shiki
pnpm remove tippy.js
```

Remove after moment migration (Phase 2): `pnpm remove moment`

**Validation:** `pnpm build` must succeed after this phase.

---

## Phase 2 -- Infrastructure Rewrites

### 2.1 Auth Store (replace useCookie)

New file: [src/stores/auth.ts](src/stores/auth.ts)

Reactive Pinia store replacing all `useCookie` calls:

- `userData: Ref<UserData | null>` (persisted to localStorage)
- `accessToken: Ref<string | null>` (NOT persisted -- Supabase manages the real token)
- `abilityRules: Ref<AppAbilityRawRule[]>` (persisted to localStorage)
- `isAuthenticated: ComputedRef<boolean>`
- Actions: `setAuth(userData, token, rules)`, `clearAuth()`, `updateAbilities(rules)`

Migration: global find-replace `useCookie('userData')` / `useCookie('accessToken')` / `useCookie('userAbilityRules')` across all files:

- [src/services/auth.ts](src/services/auth.ts) (11 useCookie calls)
- [src/plugins/1.router/guards.ts](src/plugins/1.router/guards.ts) (5 useCookie calls)
- [src/stores/org.ts](src/stores/org.ts) (4 useCookie calls)
- [src/utils/abilityRules.ts](src/utils/abilityRules.ts) (1 useCookie call)
- [src/@layouts/plugins/casl.ts](src/@layouts/plugins/casl.ts) (2 useCookie calls) -- relocate first
- Various page files (login, register, verify-email, accept-invite, auth/callback)

### 2.2 CASL Relocation and Cleanup

Move to `src/plugins/casl/`:

- Keep [src/plugins/casl/index.ts](src/plugins/casl/index.ts) -- remove all 10 console.log statements
- Keep [src/plugins/casl/ability.ts](src/plugins/casl/ability.ts) -- unchanged logic
- Move `src/@layouts/plugins/casl.ts` to `src/plugins/casl/navigation.ts` -- contains `can()`, `canViewNavMenuGroup()`, `canNavigate()` (critical auth logic)
- Replace `useCookie` calls in relocated code with auth store reads
- Rename imports from `@layouts/plugins/casl` to `@/plugins/casl/navigation`

### 2.3 Theme Config Store (rebuild)

New file: [src/stores/config.ts](src/stores/config.ts) (replaces `@core/stores/config.ts`)

Slim store managing only:

- `theme: 'light' | 'dark' | 'system'` (persisted to localStorage)
- `isNavCollapsed: boolean` (persisted to localStorage)
- `resolvedTheme: ComputedRef<'light' | 'dark'>` (handles system preference via `matchMedia`)
- `initTheme()` -- sets `document.documentElement.dataset.theme`

~40 lines. No cookies, no RTL, no footer type, no skin, no semi-dark nav.

### 2.4 Logging Wrapper

New file: [src/utils/logger.ts](src/utils/logger.ts)

```typescript
import * as Sentry from '@sentry/vue'

type LogLevel = 'info' | 'warn' | 'error'

function log(level: LogLevel, message: string, context?: Record<string, unknown>) {
  if (level !== 'info') Sentry.logger[level](message, context ?? {})
  if (import.meta.env.DEV) console[level](`[${level.toUpperCase()}] ${message}`, context ?? '')
}

export const logger = {
  info: (msg: string, ctx?: Record<string, unknown>) => log('info', msg, ctx),
  warn: (msg: string, ctx?: Record<string, unknown>) => log('warn', msg, ctx),
  error: (msg: string, ctx?: Record<string, unknown>) => log('error', msg, ctx),
}
```

Replace ALL `console.log` / `console.warn` / `console.error` across the codebase (~100+ occurrences in auth.ts, guards.ts, org.ts, CASL plugin, navigation/others.ts, etc.).

### 2.5 Moment to date-fns Migration

~21 files to update. `moment` is already alongside `date-fns` in the codebase. Common replacements:

- `moment(date).format(...)` to `format(new Date(date), ...)`
- `moment(date).fromNow()` to `formatDistanceToNow(new Date(date), { addSuffix: true })`
- `moment(date).calendar()` to `formatRelative(new Date(date), new Date())`

Files: `formatters.ts`, `agentUtils.ts`, `usePlaygroundChat.ts`, `useAgentsQuery.ts`, `useReleaseStagesQuery.ts`, `useQAQuery.ts`, `AgentQA.vue`, `SpanDetails.vue`, `RunHistoryDrawer.vue`, `EditSidebar.vue`, `HelpRequestDialog.vue`, `GlobalSecretsManager.vue`, `ChatPreview.vue`, `SharedPlayground.vue`, `super-admin.vue`, `data-sources.vue`, `organization.vue`, `verify-email.vue`, `2.gtm.ts`

Then `pnpm remove moment @types/moment`.

### 2.6 i18n Removal

- Delete `src/plugins/i18n/` directory
- Search for `$t('...')` and `t('...')` calls -- replace with plain English strings (only found in `@core` components which are deleted)
- Remove `useI18n()` imports
- Remove `VLocaleProvider` from `App.vue`
- Remove `vue-i18n` from auto-import config in vite.config.ts

### 2.7 Relocate Shared Utilities

Move from `@core` to `src/utils/`:

- `@core/utils/colorConverter.ts` to `src/utils/colorConverter.ts` (used in App.vue for hex-to-rgb)
- `@core/utils/validators.ts` to `src/utils/validators.ts` (if used)
- `@core/utils/formatters.ts` to `src/utils/formatters.ts` (if used beyond @core)
- `@core/utils/helpers.ts` -- audit and merge useful parts into existing utils
- `@core/composable/useCookie.ts` -- DELETE (replaced by auth store)

### 2.8 Split scopeoApi into Domain Modules

Split [src/services/scopeoApi.ts](src/services/scopeoApi.ts) (1,088 lines) into:

```
src/api/
  index.ts          -- barrel re-export + scopeoApi aggregate object
  workflows.ts      -- projectsApi (renamed), templatesApi
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

The `$api` base client stays in [src/utils/api.ts](src/utils/api.ts).

The barrel `src/api/index.ts` re-exports everything AND provides the `scopeoApi` aggregate object for backward compatibility during migration. Consumers can gradually switch from `scopeoApi.projects.getAll()` to `import { workflowsApi } from '@/api/workflows'`.

**Naming convention:** `projectsApi` is renamed to `workflowsApi` in the new module since "project" encompasses both workflows and agents. The `scopeoApi.projects` key is aliased to `scopeoApi.workflows` in the barrel.

### 2.9 Icon System Setup

New file: [src/plugins/icons.ts](src/plugins/icons.ts)

Keep `@iconify/vue` (open source, no licensing issue). Restructure:

- Keep icon JSON packages: `@iconify-json/tabler`, `@iconify-json/mdi`, `@iconify-json/ph`, `@iconify-json/fa`, `@iconify-json/logos`
- Create a thin `<AppIcon>` wrapper component that lazy-loads icon sets via `@iconify/vue`'s built-in async loading
- Document how to add new icon sets in cursor rules

**Validation:** `pnpm build` must succeed after this phase.

---

## Phase 3 -- Design System (Base UI Components)

Build ~25 base components in `src/components/ui/`, all using Tailwind CSS. Each component supports light/dark via CSS custom properties.

### 3.1 Critical Priority (covers 47% of instances)

These 4 replace the most Vuetify usage:

- `**UiButton`** -- replaces `VBtn` (476 instances). Props: `variant` (solid/outline/ghost/text), `color` (primary/danger/warning/success/default), `size` (sm/md/lg), `loading`, `disabled`, `icon` (icon-only mode). Renders `<button>` or `<RouterLink>`.
- `**UiIcon`** -- replaces `VIcon` (494 instances). Thin wrapper around `@iconify/vue`'s `<Icon>`. Props: `name` (string, e.g. `tabler:circle`), `size` (number, default 20). Lazy-loads icon data.
- `**UiCard`** -- replaces `VCard` + `VCardText` + `VCardTitle` + `VCardActions` + `VCardItem` + `VCardSubtitle` (731 instances combined). Compound component with slots: `<UiCard>`, `<UiCard.Header>`, `<UiCard.Body>`, `<UiCard.Footer>`. Glass variant via prop.
- `**UiDivider**` -- replaces `VDivider` (99 instances). A styled `<hr>`.

### 3.2 High Priority (covers next 31%)

- `**UiInput**` -- replaces `VTextField` (108 instances). `<input>` with label, error state, helper text. Variants: outlined (default).
- `**UiTextarea**` -- replaces `VTextarea` (41 instances).
- `**UiSelect**` -- replaces `VSelect` (41 instances). Native `<select>` for simple cases.
- `**UiChip**` -- replaces `VChip` (107 instances). Props: `color`, `closable`, `size`.
- `**UiAlert**` -- replaces `VAlert` (98 instances). Props: `type` (info/success/warning/error), `closable`.
- `**UiDialog**` -- replaces `VDialog` (92 instances). Modal with backdrop, focus trap, escape-to-close. Uses `<dialog>` element + Tailwind.
- `**UiTooltip**` -- replaces `VTooltip` (52 instances). CSS-only tooltip using `title` attr + `:hover` pseudo-element, or a lightweight JS solution for complex cases. Replaces `tippy.js`.

### 3.3 Medium Priority

- `**UiAvatar**` -- replaces `VAvatar` (30 instances). Image or initials.
- `**UiCheckbox**` -- replaces `VCheckbox` (21 instances).
- `**UiSwitch**` -- replaces `VSwitch` (10 instances).
- `**UiRadio**` / `**UiRadioGroup**` -- replaces `VRadio`/`VRadioGroup`.
- `**UiTabs**` / `**UiTab**` / `**UiTabPanel**` -- replaces `VTabs`/`VTab`/`VWindow`/`VWindowItem` (87 instances combined).
- `**UiMenu**` -- replaces `VMenu` (15 instances). Dropdown menu with positioning.
- `**UiList**` / `**UiListItem**` -- replaces `VList`/`VListItem`/`VListItemTitle`/`VListItemSubtitle` (130 instances combined).
- `**UiProgressCircular**` -- replaces `VProgressCircular` (49 instances). SVG spinner.
- `**UiProgressLinear**` -- replaces `VProgressLinear` (15 instances). Horizontal bar.
- `**UiSnackbar**` -- replaces `VSnackbar` (19 instances). Toast notification system.
- `**UiSkeleton**` -- replaces `VSkeletonLoader` (10 instances). Shimmer placeholder.
- `**UiForm**` -- replaces `VForm` (30 instances). Form wrapper with validation.
- `**UiBadge**` -- replaces `VBadge` (4 instances).

### 3.4 Layout Utilities (no components needed)

`VRow`, `VCol`, `VSpacer` (272 instances) are replaced directly with Tailwind flex/grid classes:

- `<VRow>` becomes `<div class="flex gap-4">`
- `<VCol cols="6">` becomes `<div class="w-1/2">` or grid utilities
- `<VSpacer />` becomes `<div class="flex-1">` or `ml-auto`

### 3.5 Data Table (TanStack Vue Table)

- `pnpm add @tanstack/vue-table`
- Build `**UiDataTable**` component wrapping TanStack Vue Table with Tailwind styling
- Features: sorting, pagination, row selection, custom cell renderers, skeleton loading state
- Replaces `VDataTable` (14 instances) and `VDataTableServer` (3 instances) across 9 files

### 3.6 Command Palette (replaces NavSearchBar + Shepherd)

Build `**CommandPalette**` component from scratch:

- Triggered by `Cmd+K` / `Ctrl+K`
- Modal overlay with search input
- Searches: pages (agents, workflows, knowledge, monitoring, etc.), recent items, actions (create workflow, create agent)
- Uses existing navigation data from `src/navigation/vertical/others.ts`
- Replaces current `NavSearchBar.vue` which depends on Shepherd.js and `@db` (fake-api data)

**Validation:** All 25 components render correctly in both light/dark themes.

---

## Phase 4 -- Layout System Rebuild

### 4.1 App Shell

Rebuild [src/layouts/default.vue](src/layouts/default.vue):

```
+-------+-----------------------------------+
| Side  |  Top bar (org selector, search,   |
| bar   |  theme toggle, user profile)      |
| (nav) |-----------------------------------+
|       |                                   |
|       |  <RouterView /> (page content)    |
|       |                                   |
+-------+-----------------------------------+
```

New components:

- `**AppSidebar.vue**` -- collapsible vertical nav with glass effect, replaces `VerticalNavLayout` + all `@layouts/components/Vertical*` (8 files). Props: `collapsed`, `items`. Uses CASL `can()` for visibility.
- `**AppTopbar.vue**` -- top bar with org selector, command palette trigger, theme toggle, user menu. Replaces the slot-based approach in `DefaultLayoutWithVerticalNav.vue`.
- `**AppSidebarItem.vue**` -- nav item with icon, label, active state, nested children support.
- `**AppSidebarGroup.vue**` -- collapsible group of nav items.

Keep existing navigation logic in [src/navigation/vertical/others.ts](src/navigation/vertical/others.ts) but simplify: remove the excessive console.log statements, use logger instead.

### 4.2 Blank Layout

Rebuild [src/layouts/blank.vue](src/layouts/blank.vue) -- minimal wrapper for auth pages (login, register, etc.). Just a centered content area.

### 4.3 App.vue Rewrite

Simplify [src/App.vue](src/App.vue):

- Remove `VLocaleProvider`, `VApp`, `VSnackbar` (Vuetify wrappers)
- Init theme store
- Render `<RouterView />`
- Global toast notification via `UiSnackbar` for access denied

### 4.4 Layout Components Migration

- Rebuild `OrgSelector.vue` -- dropdown to switch between organizations
- Rebuild `UserProfile.vue` -- avatar + dropdown menu with logout
- Rebuild `NavbarThemeSwitcher.vue` -- simple toggle button using config store
- Delete `NavSearchBar.vue` (replaced by CommandPalette)
- Delete `NavbarShortcuts.vue` (uses dead Shortcuts.vue from @core)
- Delete `NavBarNotifications.vue` (uses dead Notifications.vue from @core)
- Delete `DefaultLayoutWithHorizontalNav.vue` (unused)
- Rebuild `Footer.vue` -- minimal footer

**Validation:** App loads, sidebar navigation works, org selector works, theme toggle works.

---

## Phase 5 -- Page and Component Migration

### Migration Strategy

For each file:

1. Replace `<V*>` components with new `<Ui*>` components or Tailwind markup
2. Replace Vuetify utility classes (`d-flex`, `pa-4`, `text-primary`) with Tailwind equivalents
3. Replace Vuetify CSS variables (`--v-theme-primary`) with new CSS custom properties
4. Remove `:deep(.v-*)` style overrides
5. Replace `useTheme()` from vuetify with config store

**Mapping of common Vuetify classes to Tailwind:**

- `d-flex` to `flex`, `d-none` to `hidden`
- `pa-4` to `p-4`, `ma-2` to `m-2`, `gap-2` to `gap-2`
- `text-primary` to `text-primary`, `bg-surface` to `bg-surface`
- `justify-center` to `justify-center`, `align-center` to `items-center`
- `w-100` to `w-full`, `h-100` to `h-full`

### 5a. Auth Pages (6 pages)

- [src/pages/login.vue](src/pages/login.vue)
- [src/pages/register.vue](src/pages/register.vue)
- [src/pages/forgot-password.vue](src/pages/forgot-password.vue)
- [src/pages/reset-password.vue](src/pages/reset-password.vue)
- [src/pages/verify-email.vue](src/pages/verify-email.vue)
- [src/pages/accept-invite.vue](src/pages/accept-invite.vue)

These use `AppTextField` heavily. Replace with `UiInput`. Design: clean centered card, Inter font, subtle glass background.

### 5b. Core Pages (6 pages)

- [src/pages/index.vue](src/pages/index.vue) (homepage)
- [src/pages/home.vue](src/pages/home.vue)
- [src/pages/org/[orgId]/projects/index.vue](src/pages/org/[orgId]/projects/index.vue) (workflow list)
- [src/pages/org/[orgId]/projects/[id].vue](src/pages/org/[orgId]/projects/[id].vue) (workflow detail)
- [src/pages/org/[orgId]/agents/index.vue](src/pages/org/[orgId]/agents/index.vue) (agent list)
- [src/pages/org/[orgId]/agents/[id].vue](src/pages/org/[orgId]/agents/[id].vue) (agent detail)

### 5c. Domain Pages (7 pages)

- [src/pages/org/[orgId]/data-sources.vue](src/pages/org/[orgId]/data-sources.vue) (VDataTable -- migrate to UiDataTable)
- [src/pages/org/[orgId]/monitoring.vue](src/pages/org/[orgId]/monitoring.vue) (Chart.js -- restyle wrappers)
- [src/pages/org/[orgId]/scheduler/index.vue](src/pages/org/[orgId]/scheduler/index.vue)
- [src/pages/org/[orgId]/variables.vue](src/pages/org/[orgId]/variables.vue) (VDataTable)
- [src/pages/org/[orgId]/connections.vue](src/pages/org/[orgId]/connections.vue) (VDataTable)
- [src/pages/org/[orgId]/organization.vue](src/pages/org/[orgId]/organization.vue) (large -- VDataTable + many forms)
- [src/pages/admin/super-admin.vue](src/pages/admin/super-admin.vue) (VDataTable -- admin dashboard)

### 5d. Static Pages (5 pages)

- [src/pages/privacy-policy.vue](src/pages/privacy-policy.vue) (markdown rendering)
- [src/pages/terms-conditions.vue](src/pages/terms-conditions.vue) (markdown rendering)
- [src/pages/not-authorized.vue](src/pages/not-authorized.vue)
- [src/pages/[...error].vue](src/pages/[...error].vue) (404)
- [src/pages/admin/whitelist.vue](src/pages/admin/whitelist.vue)

### 5e. Complex Component Migration + Decomposition

#### EditSidebar.vue (3,365 lines to ~8 files)

Extract from [src/components/studio/components/EditSidebar.vue](src/components/studio/components/EditSidebar.vue):

- `ParameterRenderer.vue` -- renders a single parameter widget (eliminates ~600 lines of duplicated template for basic/grouped/advanced)
- `ParameterGroupCard.vue` -- collapsible group with header toggle
- `PortMappingSection.vue` -- input/output port select UI
- `ToolDescriptionEditor.vue` -- right-column tool description form
- `OptionalToolsList.vue` -- optional subcomponent toggles
- `GmailIntegrationSection.vue` -- Gmail OAuth card
- `EditSidebarHeader.vue` -- dialog header
- `EditSidebarFooter.vue` -- footer with metadata + buttons

#### SharedPlayground.vue (3,151 lines to ~6 files)

Extract from [src/components/shared/SharedPlayground.vue](src/components/shared/SharedPlayground.vue):

- `PlaygroundChatInput.vue` -- textarea + send button + file attach + keyboard
- `PlaygroundFileAttachments.vue` -- file chip display, drag-and-drop
- `PlaygroundCustomFields.vue` -- dynamic JSON/simple/file fields
- `PlaygroundVariableSetSelector.vue` -- variable set multi-select
- `PlaygroundWelcomeState.vue` -- empty conversation UI
- Remove ~773 lines of dead CSS (commented-out chat-history styles)

#### QADatasetTable.vue (2,507 lines to ~6 extractions)

Extract from [src/components/qa/QADatasetTable.vue](src/components/qa/QADatasetTable.vue):

- `useQARunOrchestration.ts` composable -- sync/async run logic, WebSocket
- `useQATestCaseState.ts` composable -- local testCases state, CRUD, lastSaved
- `QAGroundtruthCell.vue` -- inline-editable groundtruth cell
- `QACustomColumnCell.vue` -- inline-editable custom column cell
- `QAProgressBanner.vue` -- async run progress bar
- Migrate `VDataTable` to `UiDataTable` (TanStack Vue Table)

#### StudioFlow.vue (2,009 lines to ~4 composables)

Extract from [src/components/studio/StudioFlow.vue](src/components/studio/StudioFlow.vue):

- `useStudioGraphPersistence.ts` -- save, auto-save, deploy (~200 lines)
- `useStudioNodeCrud.ts` -- create, delete, edit nodes (~300 lines)
- `useStudioNavigation.ts` -- zoom, breadcrumbs, active component tracking (~200 lines)
- `StudioToolbar.vue` -- breadcrumbs + action buttons

#### Other Large Components

- [src/components/studio/inputs/FieldExpressionInput.vue](src/components/studio/inputs/FieldExpressionInput.vue) (1,075 lines) -- replace tippy.js with UiTooltip
- [src/components/agents/AgentStudioUnified.vue](src/components/agents/AgentStudioUnified.vue) (941 lines) -- migrate Vuetify
- [src/components/admin/ComponentsManager.vue](src/components/admin/ComponentsManager.vue) (871 lines) -- migrate VDataTable to UiDataTable
- [src/components/shared/SharedAPI.vue](src/components/shared/SharedAPI.vue) (845 lines) -- migrate Vuetify
- All remaining components in `src/components/` -- systematic V* to Ui* replacement

### 5f. Chart.js Wrapper Rewrite

Replace the 7 `@core/libs/chartjs/` chart wrappers with new thin wrappers in `src/components/charts/`:

- `BarChart.vue`, `LineChart.vue`, `DoughnutChart.vue`, `RadarChart.vue`, `PolarAreaChart.vue`, `BubbleChart.vue`, `ScatterChart.vue`
- Theme integration via CSS custom properties instead of Vuetify `useTheme()`
- New config helper `src/utils/chartConfig.ts` replacing `@core/libs/chartjs/chartjsConfig.ts`

### 5g. Remaining Shared Components

- Rebuild `GenericConfirmDialog.vue` (used in 13 business components) using `UiDialog`
- Rebuild `HelpRequestDialog.vue` using `UiDialog` + `UiInput`
- Rebuild `GlobalHelpButton.vue`
- Migrate `MDContent.vue` (markdown-it rendering) -- keep markdown-it, restyle
- Migrate `AppSearchHeader.vue`, `AppLoadingIndicator.vue`, `DraftnrunLogo.vue`

**Validation after each sub-phase:** App compiles, affected pages render correctly.

---

## Phase 6 -- Final Cleanup and Optimization

### 6.1 Remove Migration Scaffolding

- Remove `@core` and `@layouts` path aliases from vite.config.ts (should have zero imports by now)
- Remove `@themeConfig` alias
- Remove `unplugin-vue-define-options` (Vue 3.5 has native `defineOptions`)
- Remove `destr` if no longer needed after useCookie removal
- Remove `ufo` if NavSearchBar is replaced
- Audit and remove `@vueuse/math` if unused

### 6.2 Bundle Analysis

- Run `npx vite-bundle-visualizer` to identify large chunks
- Verify all page routes use lazy imports (they should via unplugin-vue-router)
- Ensure Chart.js, TipTap, Vue Flow, CodeMirror are code-split (async components)
- Verify `vite-plugin-vue-devtools` is only loaded in dev

### 6.3 Cleanup

- Run `pnpm build` -- fix any remaining errors
- Run `pnpm lint` -- fix style issues
- Remove all `!important` overrides from SCSS/CSS (should be zero after Vuetify removal)
- Delete `src/assets/styles/variables/` (Vuetify SCSS variables)
- Delete `src/assets/styles/styles.scss` (empty)
- Delete `src/styles/landing-page.scss` (integrate into page-level Tailwind)
- Remove `auto-imports.d.ts` and `components.d.ts` from git (they're auto-generated)
- Clean up `typed-router.d.ts`, `env.d.ts`, `shims.d.ts` if needed
- Remove `.stylelintrc.json` and `stylelint` dependencies (Tailwind uses utility classes, no custom SCSS to lint)

---

## Phase 7 -- Testing

### 7.1 Unit Tests for UI Components

Create `src/components/ui/__tests__/` with Vitest tests for all 25 base components:

- Rendering with default props
- All variant/color/size combinations
- Event emission (click, change, close)
- Slot content rendering
- Dark mode class application
- Accessibility (ARIA attributes, keyboard navigation)

### 7.2 Integration Tests

- Auth flow: login, logout, session recovery, route guards
- Navigation: sidebar rendering based on CASL permissions, org switching
- Theme: dark/light toggle persists and applies
- API modules: verify barrel exports match old scopeoApi interface

### 7.3 Composable Tests

- Test extracted composables: `useStudioGraphPersistence`, `useStudioNodeCrud`, `useStudioNavigation`, `useQARunOrchestration`, `useQATestCaseState`
- Test auth store: setAuth, clearAuth, persistence

**Target:** Full coverage of new code, light smoke tests for migrated pages.

---

## Phase 8 -- Documentation and Cursor Rules

### 8.1 README.md Rewrite

Complete rewrite of [README.md](README.md):

- Project overview (Draft'n Run frontend -- Vue 3 + Tailwind)
- Tech stack (Vue 3, Tailwind CSS, Pinia, TanStack Query, TanStack Table, Supabase, Sentry, Chart.js, Vue Flow, TipTap, CASL)
- Project structure with directory tree
- Getting started (prerequisites, env setup, dev server, build)
- Design system overview (tokens, components, theming)
- Architecture decisions (auth flow, API layer, state management)
- Deployment (Netlify + Docker)

### 8.2 Cursor Rules

Rewrite/create `.cursor/rules/` files:

`**back-office-architecture.mdc`:**

- Directory structure map
- Component naming conventions (`Ui`* for base, `App`* for app-level)
- Composable patterns (queries in `composables/queries/`, domain logic as composables)
- API module pattern (one file per domain in `src/api/`)
- State management (auth store, org store, config store -- no other global stores)

`**back-office-styling.mdc`:**

- Always use Tailwind utility classes, never raw CSS unless absolutely necessary
- Use CSS custom properties from `tokens.css` for theme-aware colors
- Component props for variants, not CSS overrides
- Dark mode via `data-theme` attribute, not class-based
- Max component size: 400 lines -- extract sub-components or composables beyond that

`**back-office-practices.mdc`:**

- ALWAYS update README and cursor rules when adding/removing screens, routes, components, or patterns
- Use `logger.`* instead of `console.`* (enforced by ESLint rule)
- Use TanStack Query for all server state -- no manual fetch + useState patterns
- Use `UiDataTable` (TanStack Table) for all tabular data
- Error handling: never bare `catch {}`, always log to Sentry
- No dead code: remove unused imports, components, and commented-out blocks in every PR
- Test new components and composables

### 8.3 Design System Documentation

Create `src/components/ui/README.md`:

- Component inventory with props, slots, and usage examples
- Design tokens reference
- Theming guide (how to modify colors, add new tokens)
- Icon system (how to add new icon sets)

---

## File Change Summary

- **Files deleted:** ~230 (139 @core + 29 @layouts + 36 fake-api + 16 dialogs + 10 misc dead files)
- **Files created:** ~45 (25 UI components + tests + 16 API modules + stores + config + docs)
- **Files modified:** ~185 (all files with Vuetify components or @core/@layouts imports)
- **NPM packages removed:** ~30
- **NPM packages added:** ~5
- **Net LOC change:** estimated -15,000 to -20,000 lines removed

## Validation Commands

After each phase:

- `pnpm build` -- must succeed with zero errors
- `pnpm lint` -- must pass
- `pnpm test` -- must pass
- Manual smoke test: login, navigate sidebar, open a workflow, open an agent, check monitoring charts

