---
description: Icon system — three tiers (library sets, custom brand SVGs, Vuetify form overrides)
globs: src/plugins/vuetify/icons.ts, src/assets/images/iconify-svg/**, src/components/studio/utils/node-factory.utils.ts
alwaysApply: false
---

# Icon System

All icon rendering flows through **Iconify** (`@iconify/vue`). The system has three tiers:

## 1. Library icon sets (vast majority of icons)

Installed as `@iconify-json/*` packages — available everywhere via `<VIcon>` or `<Icon>`.

| Package              | Prefix (Iconify) | Prefix (VIcon) | Usage                        |
| -------------------- | ----------------- | -------------- | ---------------------------- |
| `@iconify-json/tabler` | `tabler:`       | `tabler-`      | Primary UI icons             |
| `@iconify-json/mdi`    | `mdi:`          | `mdi-`         | Material Design extras       |
| `@iconify-json/ph`     | `ph:`           | `ph-`          | Phosphor icons               |
| `@iconify-json/fa`     | `fa6-solid:`    | `fa-`          | Font Awesome                 |
| `@iconify-json/logos`  | `logos:`        | `logos-`       | Brand/service logos (Gmail, Slack, HubSpot…) |

VIcon normalizes dash-prefixed names to colon-prefixed via `iconNameToIconify()` in `src/plugins/vuetify/icons.ts`.

**When to use:** Always check the library sets first. Browse at https://icon-sets.iconify.design/.

## 2. Custom brand SVGs (`custom:` prefix)

For brand icons that do NOT exist in any Iconify library set (e.g., Microsoft Outlook).

| File location | `src/assets/images/iconify-svg/<name>.svg` |
| Registered as | `custom:<name>` (auto-registered at startup) |
| Backend stores as | `custom-<name>` (dash-separated) |
| Resolved by | `isProviderLogo()` in `node-factory.utils.ts` → Iconify `<Icon>` component |

### How to add a new custom brand icon

1. Drop the SVG file into `src/assets/images/iconify-svg/` (e.g., `my-brand.svg`).
2. That's it — `icons.ts` auto-discovers all `*.svg` files in that directory via `import.meta.glob` and registers each as `custom:<filename>`.
3. In the backend seed, set `icon="custom-my-brand"` on the component.
4. `isProviderLogo()` already matches the `custom` prefix, so the studio graph will render it via the Iconify `<Icon>` component.

### How it works

- `icons.ts` uses `import.meta.glob('@images/iconify-svg/*.svg', { eager: true, query: '?raw' })` to load all SVGs at build time.
- Each SVG is parsed, its `viewBox` is extracted, and it's registered with `addIcon('custom:<name>', ...)`.
- The backend value `custom-<name>` is interpreted by Iconify as prefix `custom`, name `<name>` (first dash = separator).

### CRITICAL — do not delete this directory or its files during refactors/migrations

The `src/assets/images/iconify-svg/` directory and the auto-registration loop in `icons.ts` are load-bearing.
Removing them silently breaks all `custom-*` component icons in the studio graph.

## 3. Vuetify form-control SVG overrides

Custom SVG components that replace default Vuetify checkbox/radio icons. Located in `src/assets/images/svg/` and mapped in `vuetifyFormSvgs` in `icons.ts`. Unrelated to the Iconify icon system.

## Studio graph icon rendering (`isProviderLogo`)

`src/components/studio/utils/node-factory.utils.ts` exports `isProviderLogo(icon)`:

- Returns `true` if icon starts with `logos` or `custom` → rendered by Iconify `<Icon>` (preserves original colors).
- Returns `false` → rendered by `<VIcon>` (themed with `color="primary"`).

This function is used in `SpecialNode.vue`, `RouterNode.vue`, `EditSidebar.vue`, `ComponentSelectionCarousel.vue`, and `AgentStudioUnified.vue`.

## Files involved

| File | Role |
| ---- | ---- |
| `src/plugins/vuetify/icons.ts` | Icon config: library prefix mapping, custom SVG auto-registration, Vuetify form overrides |
| `src/assets/images/iconify-svg/` | Custom brand SVG files (auto-discovered) |
| `src/assets/images/svg/` | Vuetify form-control SVG overrides |
| `src/components/studio/utils/node-factory.utils.ts` | `isProviderLogo()` — determines rendering path in studio graph |
| `package.json` | `@iconify-json/*` library set dependencies |
