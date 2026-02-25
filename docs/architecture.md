# Architecture

## Scope

This document describes:

1. Current runtime architecture in this repository.
2. Target architecture model for AI-first evolution.
3. Allowed dependency directions.

If this file conflicts with `AGENTS.md`, this file wins.

## Current Layout (As-Is)

- `routers/`: HTTP entrypoints (Quart blueprints).
- `services/`: use-case orchestration and application logic.
- `other/`: integrations and utility adapters (Stellar, Grist, Telegram, cache).
- `db/`: persistence concerns.
- `templates/`, `static/`: UI layer.
- `start.py`: composition root.

Current dependencies are partially enforced by `.linters/arch_test.py`.

## Target Model (To-Be)

Dependency direction (inward only):

```text
domain <- application <- infrastructure
                     <- interface
```

Target mapping for this repository:

- `domain` (new target package): pure business rules, no framework/db/network imports.
- `application` (target shape of `services/`): use-cases + ports interfaces.
- `infrastructure` (target shape of `other/` + `db/`): implementations of ports.
- `interface` (target shape of `routers/` + templates binding): transport layer.

## Layer Rules

Mandatory rules for new code and migrations:

1. `domain` must not import `application`, `infrastructure`, or `interface`.
2. `application` may import `domain`, but not concrete infrastructure adapters.
3. `interface` may call `application` use-cases only.
4. `infrastructure` may depend on `application` ports and external SDKs.
5. Composition/wiring happens in boundary modules (entrypoints/factories).

## Migration Strategy

Use iterative migration per feature:

1. Isolate business logic in `services/` into explicit use-case functions.
2. Extract external calls behind port-like interfaces.
3. Move pure logic into `domain` modules.
4. Extend `.linters/arch_test.py` as directory structure matures.

Migration is incremental by touch: when a file changes for business reasons, it must move one step closer to the target model.
Use `just check-changed` for fast non-degradation checks on changed Python files.

Large moves follow expand -> migrate -> contract.
