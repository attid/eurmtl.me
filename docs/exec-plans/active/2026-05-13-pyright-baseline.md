# Pyright baseline

## Goal

Make `just check` deterministic by declaring the repository's current pyright baseline explicitly.

## Scope

- Add pyright configuration to project tooling.
- Keep checking the full repository.
- Do not suppress formatting, lint, tests, or architecture checks.

## Checks

- Run `just check`.

## Results

- `just types`: passed with `0 errors, 0 warnings, 0 informations`.
- `just check`: passed after pinning pyright and filtering an external sqlite deprecation warning from `aiosqlite`.
