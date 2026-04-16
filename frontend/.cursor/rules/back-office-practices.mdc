---
description: Draft'n Run frontend coding practices — logging, data fetching, error handling, documentation hygiene
globs: ['src/**']
alwaysApply: false
---

# Back-office practices

## Documentation hygiene

Every code change MUST update affected documentation in the same diff:
- Add/remove/rename a screen, route, component, or pattern → update `README.md` and relevant cursor rules.
- Never let docs or rules drift from the code.

## Logging

Use `logger.info()`, `logger.warn()`, `logger.error()` from `src/utils/logger.ts`.
Never use bare `console.log/warn/error` — the logger integrates with Sentry automatically.

## Data fetching

- All server reads through TanStack Query composables in `src/composables/queries/`.
- Mutations use `useMutation()`.
- Inline edits: patch cache with `queryClient.setQueryData()` — never `invalidateQueries` for typing/toggling/field updates.
- Destructive/structural changes (delete, reorder, bulk ops): `invalidateQueries` is fine.
- Never store API data in manual `ref()` — always TanStack Query.

## Notifications

Use `useNotifications()` for user-facing toasts:
```typescript
const { notify } = useNotifications()
notify.success('Saved')
notify.error('Something went wrong')
```
Never use `window.alert()` or bare `console` for user feedback.

## Error handling

- Never use bare `catch {}` — always capture the error and handle it.
- Catch specific error types when possible; use `if` checks over try/catch when the check is simple.
- When re-throwing, make the message explicit enough to debug later.
- User-facing errors: show via `notify.error()`.
- Unexpected errors: log via `logger.error()` (auto-reports to Sentry).

## Dead code

No dead code — ever. Remove:
- Commented-out blocks
- Unused imports / variables / functions
- Abandoned TODOs
- Unreachable branches

When you spot dead code during a change, delete it in the same diff.

## Testing

- Test new components and composables with Vitest.
- Test files live next to their source in `__tests__/` directories.
- Run `pnpm test` to verify.

## TypeScript

- Strict mode — no `any` unless documented.
- Use `interface` for object shapes, `type` for unions/intersections.
- Define props/emits with generic type parameter syntax.

## Import order

1. Vue / core (`vue`, `vue-router`, `pinia`)
2. Third-party libraries
3. Local components
4. Composables
5. Utils / helpers
6. Types

## Before committing

```bash
pnpm fix        # format + lint
pnpm typecheck  # catch type errors
pnpm test       # run tests
```
