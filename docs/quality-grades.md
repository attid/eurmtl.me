# Quality Grades

## Scale

- A: predictable, test-covered, boundaries enforced.
- B: mostly stable, some legacy friction.
- C: works, but weak structure or observability.
- D: high-risk area, urgent cleanup needed.

## Current Snapshot

| Area | Grade | Notes |
| --- | --- | --- |
| Routing (`routers/`) | B | Feature split is mostly clear; cross-layer coupling still exists. |
| Application (`services/`) | C | Use-cases exist, but contracts and boundaries are inconsistent. |
| Integrations (`other/`) | C | Rich utility set, but adapter boundaries are implicit. |
| Persistence (`db/`) | C | Works in practice; architectural contract not formalized. |
| UI (`templates/`, `static/`) | B | Mature templates, mixed concerns in JS handlers. |
| Documentation (`docs/`) | C -> B | AI-first baseline introduced; needs continuous updates. |
| Guardrails (`.linters/`, CI) | C | Baseline `arch-test` is in place; needs deeper import-cycle checks. |

## Upgrade Strategy

1. Raise `Guardrails` to B by adding cycle detection and richer layer import checks.
2. Raise `services/` to B by formalizing use-case and port boundaries.
3. Raise `docs/` to A by linking docs updates to CI checks.
