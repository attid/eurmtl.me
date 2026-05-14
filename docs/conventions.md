# Conventions

## Code Style

- Python 3.12, 4 spaces, explicit types where practical.
- Naming: `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- Keep files focused; avoid mixing transport, business logic, and integration code.
- Prefer explicit data structures and validation at system boundaries.

## Existing Tooling Baseline

- Format check: `just fmt` (`ruff format --check`).
- Format: `just format` (`ruff format`).
- Lint: `just lint` (`ruff check`).
- Types: `just types` (`pyright`).
- Tests: `just test` (`pytest`).
- Fast tests: `just test-fast`.
- Architecture checks: `just arch-test`.
- Changed-file checks: `just check-changed`.
- Full gate: `just check`.

## Preferred Development Pattern

For behavior changes:

1. Add or update test first.
2. Implement minimal change.
3. Run focused tests.
4. Run full relevant checks (`lint`, `types`, `test`).

For docs/process changes:

1. Create or update an execution plan in `docs/exec-plans/active/`.
2. Update source-of-truth docs.
3. Run at least syntax/style checks relevant to changed files.

Execution plan trigger:

- If there is doubt whether an execution plan is required, ask the user before editing.
- If a change touches 2+ source code, test, template, or script files and is not pure formatting, an execution plan is required.
- Markdown-only changes do not require an execution plan by themselves.
- Pure formatting means no behavior, contract, documentation, test, workflow, or architecture change.

## Touched-File Policy

- Every touched file follows non-degradation: no new lint, formatting, or boundary violations.
- Every touched file should get at least one small improvement toward target architecture.
- Local legacy cleanup is expected when it is cheap and directly adjacent to the change.
- Avoid broad cleanup in unrelated files; migrate incrementally by touch.

## Web/UI Conventions

- Preserve current template patterns and structure unless migration is explicitly requested.
- In templates, prefer explicit inline handler style (`onclick`, `onsubmit`, `oninput`, etc.) so behavior is visible in HTML.
- Do not introduce `addEventListener` in templates when the same behavior can be expressed with inline handlers.
- `addEventListener` is allowed only when inline handlers are genuinely insufficient, and only after multiple failed attempts to express the behavior with explicit HTML handlers.
- Keep JS behavior deterministic and avoid hidden global mutations.
- Any user-triggered action must provide visible feedback in the UI.
- If the end result may look unchanged, show a distinct transient state first so the user can see that the action really ran.

## Anti-Patterns

- Direct cross-layer calls that bypass use-case boundaries.
- Dynamic imports for core business paths.
- Silent exception swallowing.
- Massive formatting-only diffs unrelated to task intent.
