# Contracts Section

## Purpose

`/contracts` is a manually curated section for Soroban contracts that get a human-friendly UI.
Nothing is auto-discovered. Every contract, block, field, and action is explicitly allowlisted in Python.

## Current layout

- `routers/contracts.py` - HTTP routes for contract pages, prepare flow, callback, status.
- `services/contracts/registry.py` - manual allowlist of supported contracts.
- `services/contracts/handlers/` - contract-specific behavior.
- `services/contracts/flow_service.py` - in-memory TTL flow state for SEP-7 signing.
- `other/stellar_soroban.py` - Soroban RPC helpers (read / prepare / submit).
- `templates/contracts_list.html` - contracts index page.
- `templates/contract_detail.html` - single contract page rendered from blocks.

## Page model

Each contract has one page and that page is composed from blocks.
A block should have:
- `name`
- `title`
- `description`
- optional `fields`

Current block types are implemented manually in the template/handler flow:
- `message` - read-only block
- `capture` - write form block
- `pool_overview` - read-only pool metadata block
- `exact_in` - quote + SEP-7 swap form for exact-in swaps
- `exact_out` - quote + SEP-7 swap form for exact-out swaps

## Add a new contract

1. Create or extend a handler in `services/contracts/handlers/`.
2. Add a registry entry in `services/contracts/registry.py`.
3. Define:
   - `contract_id`
   - `title`
   - `description`
   - `public`
   - `blocks`
4. If the contract needs write actions, add the contract-specific prepare/validation helpers in its handler.
5. Reuse the common flow in `routers/contracts.py` and `services/contracts/flow_service.py` when possible.
6. Add tests for routing, metadata, and contract-specific behavior.

## Add a new block

Add the block to the contract definition in the registry/handler metadata.
Then update:
- `templates/contract_detail.html` for rendering
- the contract handler if the block needs new behavior
- router endpoints if the block needs a new action

Keep block descriptions short and user-facing.

## Add a new field

Field metadata currently supports these shapes:
- `address`
- `i128`
- `u128` (typically human-readable decimals converted in handler logic)
- `string`

When adding a field:
1. Add it to the block `fields` list in the desired order.
2. Update contract-specific validation logic.
3. Update contract-specific parameter serialization in the handler.
4. If the field should persist in browser session UX, wire it through Quart `session` explicitly.

## Read-only quote flow

For read-only quote actions:
1. Convert human input to on-chain token units if needed.
   Current swap input accepts both `.` and `,` as decimal separators via the shared numeric normalization path.
2. Call the contract via `simulateTransaction`.
3. Convert result back to human-readable values.
4. Return compact JSON for the page block.

## Write flow

For write actions:
1. Validate form input.
2. Build and prepare the Soroban transaction.
3. Generate SEP-7 URI with callback to `/contracts/callback/<request_id>`.
4. Store transient flow state in `ContractsFlowService`.
5. On callback, submit signed XDR to Soroban RPC and store the result.
6. Poll status from `/contracts/flow/<request_id>/status`.

For the current swap contract:
- `exact_in` prepares `swap(user, in_idx, out_idx, amount_in, min_amount_out)`.
- `exact_out` prepares `swap_strict_receive(user, in_idx, out_idx, amount_out, max_amount_in)`.
- Protection values (`min_amount_out` / `max_amount_in`) are derived from a fresh server-side quote at prepare time.
- The UI currently exposes slippage presets: `1%`, `3%`, `5%`.
- Prepared SEP-7 transactions currently use a 5-minute validity window.

## Direct signed-XDR submit helper

There is also a hidden helper page at `/contracts/send`.
It is intentionally not linked from the contracts index.

The page contains:
- a textarea for `signed_xdr`
- a send button
- a result block with `tx_hash` or error text

Expected form field:
- `signed_xdr`

Behavior:
- validates base64
- submits the signed Soroban transaction via Soroban RPC
- polls transaction status briefly after submit instead of assuming immediate finality
- shows `tx_hash` on success
- shows decoded transaction errors when the network rejects the transaction (for example `txTOO_LATE`)

## Limitations of the current version

- Flow state is in-memory only.
- Active signing flows are lost on process restart.
- Contracts are allowlisted manually.
- The first contract implementation is the reference pattern for the next contracts; extend by copy-with-improvement, not by inventing dynamic magic.
