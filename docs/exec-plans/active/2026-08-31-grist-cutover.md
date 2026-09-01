# Grist cutover

## Scope

- Move all Montelibero Grist bindings used by `eurmtl.me` to
  `https://grist.eurmtl.me/api/docs` and the audited document IDs.
- Keep RELY on `https://mtl-rely.getgrist.com/api/docs` with document
  `kceNjvoEEihSsc8dQ5vZVB` and a separate runtime credential.
- Preserve `/grist/webhook`, `/grist/webhook/<table_name>`, and
  `/rely/grist-webhook` behavior without registering external webhooks.

## Implementation

- [x] Update document configuration and make Grist credentials explicit per API
  client.
- [x] Configure RELY with `RELY_GRIST_TOKEN` while retaining the existing
  webhook authentication contract.
- [x] Update configuration examples and focused tests.
- [x] Run focused tests and proportionate static checks.

## Verification

- [x] Assert Montelibero request URLs use the new host and IDs.
- [x] Assert RELY request URLs use the old host and its document ID.
- [x] Assert the two API clients retain independent Authorization headers.
- [x] Confirm unrelated dirty worktree changes remain untouched.
