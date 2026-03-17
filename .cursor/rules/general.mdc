---
alwaysApply: true
---

## General

- We use uv to run python code in this project.
- We have a low comment policy → avoid comments in the code. Only add comments when it's really necessary.
- Always position imports at the top of the file.
- When you are reported a bug that wasn't found by the pytests, write a new test case after fixing the bug.
- Line length: 119 chars (matches ruff config).

## Meta-rule

Every code change MUST include updates to affected documentation (`ada_backend/docs/`, README files) and cursor rules (`.cursor/rules/`) in the same change. If you add/remove/rename a route, tool, component, or architectural pattern, update the relevant docs and rules immediately.

## Error Handling

- Never bare `except` — always specify the exception type.
- Never bare `except Exception` without logging — always log to Sentry or the logger.
- Use `if` checks instead of try/catch when the check is straightforward.

## No Dead Code

- No commented-out code blocks.
- No unused imports or variables.
- No abandoned TODOs without a tracking issue.

## Testing

- Framework: pytest. Run with `uv run pytest`.
- Write regression tests for every bug fix.

## Domain-Specific Rules

See `.cursor/rules/architecture.mdc` (always-on architecture context), and domain rules: `auth.mdc`, `engine.mdc`, `routers.mdc`, `services.mdc`, `mcp.mdc`.
