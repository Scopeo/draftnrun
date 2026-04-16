---
description: Draft'n Run frontend styling — Vuetify theming, design tokens, CSS conventions
globs: ['src/**/*.vue', 'src/**/*.scss']
alwaysApply: false
---

# Back-office styling

## Vuetify first

Use Vuetify components and their built-in props/classes for all UI.
Prefer Vuetify utility classes (`pa-4`, `mt-2`, `text-primary`, `bg-surface`) over custom CSS.
Only write custom SCSS when Vuetify doesn't cover the need.

## Design tokens

Colors and Vuetify component defaults: `src/plugins/vuetify/theme.ts` and `defaults.ts`.
Spacing, layout dimensions, and occasional global Vuetify adjustments (card actions, pill-tab typography, etc.): `src/assets/styles/variables/_tokens.scss`.

Never hard-code color hex values in components — use theme tokens via:
- Vuetify props: `color="primary"`, `color="error"`
- CSS variables: `rgb(var(--v-theme-primary))`, `rgb(var(--v-theme-surface))`
- Utility classes: `text-primary`, `bg-surface`

### Color palette (light theme)

| Token       | Value     | Note                          |
| ----------- | --------- | ----------------------------- |
| primary     | `#22577A` | Brand color — do not change   |
| secondary   | `#38A3A5` |                               |
| success     | `#2E7D32` |                               |
| info        | `#1976D2` |                               |
| warning     | `#F59E0B` |                               |
| error       | `#EF4444` |                               |
| background  | `#FAF9F7` | Warm off-white                |
| surface     | `#FDFCFA` | Warm white                    |

Grey scale uses **stone** (warm) tones, not zinc (cool).

### Design feel

The design follows a "calm technology" aesthetic inspired by Anthropic/Claude:
- Warm stone greys instead of cool zinc
- Subtle borders (`border-opacity: 0.05`), minimal shadows
- Outlined fields use softened borders (`--v-field-border-opacity: 0.18` in `_tokens.scss`) to avoid heavy "black rectangle" outlines
- Soft hover states (background tint, not border glow)
- Generous spacing and deliberate transitions (`0.2s ease-out`)
- Serif headings + sans-serif body for a literary, sophisticated feel

## Fonts

- **Headings:** Source Serif 4 (serif) via `@fontsource/source-serif-4`
- **Body:** DM Sans (sans-serif) via `@fontsource/dm-sans`

Both loaded globally in `main.ts`. Do not import additional fonts without discussion.

## Component size

Max ~400 lines per `.vue` file.
Extract sub-components or composables when approaching the limit.

## CSS rules

- **No `!important`** on Vuetify internal classes — override via specificity or theme config instead.
- **Scoped styles:** Always use `<style lang="scss" scoped>` unless styling must leak (rare).
- **No inline styles** — use Vuetify classes or scoped SCSS.
- **BEM naming** for custom classes: `.my-component__element--modifier`.
- **No global style sheets** for one-off component styling — use scoped SCSS. Recurring patterns shared across screens (e.g. `.v-tabs-pill` tab labels) may live in `_tokens.scss` with a short comment.

## Dark mode

The app supports light / dark / system theme cycling (config store).
Always test both themes when adding visual changes.
Use Vuetify theme-aware tokens so dark mode works automatically.
