# Glossary

## Terms

- **Agent-first**: Development mode where AI agents can execute tasks autonomously under strict repo guardrails.
- **Execution plan**: Task contract in `docs/exec-plans/active/` used before non-trivial implementation.
- **Domain**: Business rules independent from transport, DB, or external APIs.
- **Application**: Use-case orchestration that coordinates domain logic and ports.
- **Infrastructure**: External adapters (DB/API/cache/SDK) implementing application ports.
- **Interface**: Input/output layer (HTTP handlers, templates, CLI) invoking use-cases.
- **Port**: Abstract contract declared in application layer for external dependencies.
- **Guardrail**: Mechanical check (lint/test/CI rule) preventing architectural or process drift.
- **Quality grade**: A-D score per area that tracks architectural health over time.
- **ADR**: Architecture Decision Record documenting context, choice, and consequences.
