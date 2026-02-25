# ai-first-bootstrap: Establish AI-first docs baseline

## Context

Repository has `AI_FIRST.md` contract draft, but source-of-truth docs and index were missing or incomplete.
Goal: create minimal baseline documentation to make future changes predictable and checkable.

## Plan changes

1. [x] Align `AGENTS.md` with AI-first index format.
2. [x] Add missing core docs under `docs/` (architecture, conventions, principles, grades, glossary).
3. [x] Link new docs from `README.md`.
4. [x] Create ADR for decision to adopt docs-first baseline.
5. [x] Add baseline guardrail commands in `justfile` (`fmt`, `test-fast`, `arch-test`, `check`).
6. [x] Add touched-file migration policy and `check-changed` guardrail.
7. [ ] Move this plan to `docs/exec-plans/completed/` after follow-up phase and CI guardrails setup.

## Risks and Open Questions

- `just metrics` is still not implemented.
- `arch-test` currently validates baseline docs/rules and should be expanded as architecture migration progresses.

## Verification

- Manual verification that referenced docs exist and paths are valid.
- Optional follow-up: `just lint`, `just types`, `just test` (no runtime logic changed).
