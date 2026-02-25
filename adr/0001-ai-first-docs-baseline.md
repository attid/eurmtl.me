# ADR-0001: Adopt AI-first docs baseline

## Status

Accepted

## Context

The repository has active AI-assisted development, but key project knowledge was spread across ad-hoc files.
This created ambiguity for autonomous changes and made process enforcement harder.

## Decision

Adopt a docs-first baseline aligned with `AI_FIRST.md`:

- Keep `AGENTS.md` as a short index.
- Store detailed architecture/process standards under `docs/`.
- Require execution plans in `docs/exec-plans/active/` for non-trivial tasks.
- Track architectural quality debt in `docs/quality-grades.md`.

## Consequences

Positive:

- Lower ambiguity for agents and reviewers.
- Better onboarding and predictable task execution.
- Clear place for future mechanical checks.

Trade-offs:

- Higher documentation maintenance overhead.
- Need follow-up work to implement CI/linters for full mechanical enforcement.
