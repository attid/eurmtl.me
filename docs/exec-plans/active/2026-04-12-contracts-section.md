# Contracts Section Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a new `/contracts` section for manually allowlisted Soroban contracts with one initial contract page, two blocks (`message` and `capture`), SEP-7 signing flow, in-memory request state, and developer documentation for adding new contracts and fields.

**Architecture:** Add a dedicated `routers/contracts.py` interface layer backed by a small `services/contracts/` application layer. Keep contract definitions explicitly allowlisted in a Python registry, keep contract-specific behavior in a handler module, and isolate Soroban RPC/build/submit logic in `other/stellar_soroban.py`. Use in-memory TTL state for signing flows and session for user-scoped hints like last-used address.

**Tech Stack:** Quart blueprints/templates, pytest/pytest-asyncio, Stellar SDK Soroban RPC + SEP-7 URI support, cachetools TTLCache, existing session/test fixture patterns.

---

### Task 1: Add failing router tests for the contracts entrypoints

**Files:**
- Create: `tests/routers/test_contracts.py`
- Modify: `tests/fixtures/app.py`
- Test: `tests/routers/test_contracts.py`

**Step 1: Write the failing tests**

Add tests for:
- `GET /contracts` returns 200 and includes the first contract title.
- `GET /contracts/<contract_id>` returns 200 and renders both block titles/descriptions.
- hidden contracts are reachable by direct URL but not listed in `/contracts`.
- `GET /contracts/UNKNOWN` returns 404.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/routers/test_contracts.py -v`
Expected: FAIL because the blueprint/routes do not exist yet.

**Step 3: Write minimal implementation**

Create minimal contracts registry, minimal router, and register the blueprint in test app/startup.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/routers/test_contracts.py -v`
Expected: PASS.

### Task 2: Add failing unit tests for the contracts registry and page model

**Files:**
- Create: `tests/services/test_mountain_contract.py`
- Create: `services/contracts/registry.py`
- Create: `services/contracts/handlers/mountain_contract.py`
- Test: `tests/services/test_mountain_contract.py`

**Step 1: Write the failing tests**

Add tests for:
- the first contract is present in the allowlist registry.
- the contract declares exactly two blocks: `message` and `capture`.
- `capture` block field metadata includes `user`, `amount`, and `msg` in the expected order.
- a helper chooses candidate address priority correctly (detected address before session address, session address before empty).

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/services/test_mountain_contract.py -v`
Expected: FAIL because the modules do not exist yet.

**Step 3: Write minimal implementation**

Implement simple dataclass/dict-based registry and the first contract handler metadata.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_mountain_contract.py -v`
Expected: PASS.

### Task 3: Add failing tests for Soroban read support (`message`)

**Files:**
- Create: `tests/services/test_stellar_soroban.py`
- Create: `other/stellar_soroban.py`
- Modify: `services/contracts/handlers/mountain_contract.py`
- Test: `tests/services/test_stellar_soroban.py`

**Step 1: Write the failing tests**

Add tests for:
- `load_message` delegates to the Soroban adapter with the configured RPC URL, contract id, and function name `message`.
- adapter result is normalized into a text payload suitable for the template.
- adapter exceptions are surfaced as controlled error messages.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/services/test_stellar_soroban.py tests/services/test_mountain_contract.py -v`
Expected: FAIL because read adapter/handler behavior is missing.

**Step 3: Write minimal implementation**

Implement a thin Soroban adapter for read calls and wire it into the mountain contract handler.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_stellar_soroban.py tests/services/test_mountain_contract.py -v`
Expected: PASS.

### Task 4: Add failing tests for in-memory flow state and address hints

**Files:**
- Create: `tests/services/test_contracts_flow_service.py`
- Create: `services/contracts/flow_service.py`
- Test: `tests/services/test_contracts_flow_service.py`

**Step 1: Write the failing tests**

Add tests for:
- flow creation returns a `request_id` and stores contract/action/form metadata.
- flow lookup is scoped to the originating session marker.
- updating flow status stores success payload, tx hash, and error fields.
- saving last-used address writes to session-friendly helpers.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/services/test_contracts_flow_service.py -v`
Expected: FAIL because flow service does not exist yet.

**Step 3: Write minimal implementation**

Implement TTL-backed in-memory store helpers and session-scoped access checks.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_contracts_flow_service.py -v`
Expected: PASS.

### Task 5: Add failing tests for prepare/SEP-7/status router endpoints

**Files:**
- Modify: `tests/routers/test_contracts.py`
- Modify: `routers/contracts.py`
- Modify: `services/contracts/flow_service.py`
- Modify: `services/contracts/handlers/mountain_contract.py`
- Test: `tests/routers/test_contracts.py`

**Step 1: Write the failing tests**

Add tests for:
- `POST /contracts/<contract_id>/actions/capture/prepare` validates payload and returns `request_id`, `uri`, and modal metadata.
- a valid prepare request stores `last_used_address` in session.
- `GET /contracts/flow/<request_id>/status` returns the current flow state for the same session.
- status lookup from another session is rejected.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/routers/test_contracts.py -v`
Expected: FAIL because prepare/status endpoints are not implemented.

**Step 3: Write minimal implementation**

Implement router endpoints, payload validation, flow creation, and SEP-7 URI creation using prepared transaction XDR.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/routers/test_contracts.py -v`
Expected: PASS.

### Task 6: Add failing tests for callback + Soroban submit/poll flow

**Files:**
- Modify: `tests/routers/test_contracts.py`
- Modify: `tests/services/test_stellar_soroban.py`
- Modify: `routers/contracts.py`
- Modify: `other/stellar_soroban.py`
- Modify: `services/contracts/flow_service.py`
- Test: `tests/routers/test_contracts.py`

**Step 1: Write the failing tests**

Add tests for:
- `POST /contracts/callback/<request_id>` accepts signed XDR and marks flow submitted with tx hash when submit succeeds.
- callback stores a failure payload when submit/poll fails.
- callback rejects malformed base64.
- callback rejects unknown or foreign-session flow ids.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/routers/test_contracts.py tests/services/test_stellar_soroban.py -v`
Expected: FAIL because callback/submit behavior is incomplete.

**Step 3: Write minimal implementation**

Implement signed-XDR submit and poll helpers in the Soroban adapter and wire callback handling into the flow service/router.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/routers/test_contracts.py tests/services/test_stellar_soroban.py -v`
Expected: PASS.

### Task 7: Add contract templates and wire page rendering

**Files:**
- Create: `templates/contracts_list.html`
- Create: `templates/contract_detail.html`
- Modify: `routers/contracts.py`
- Test: `tests/routers/test_contracts.py`

**Step 1: Write or update failing tests**

Extend router tests to assert rendered HTML includes:
- contract title and description
- block titles and short descriptions
- message result placeholder
- capture form fields and SEP-7 modal container

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/routers/test_contracts.py -v`
Expected: FAIL because templates are not present or do not render required elements.

**Step 3: Write minimal implementation**

Add minimal templates following current Tabler patterns and render both blocks on one page.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/routers/test_contracts.py -v`
Expected: PASS.

### Task 8: Register the blueprint in production startup

**Files:**
- Modify: `start.py`
- Test: `tests/fixtures/app.py`, `tests/routers/test_contracts.py`

**Step 1: Add a failing integration expectation if needed**

If startup registration is not already covered by app fixture tests, add a smoke test asserting `/contracts` is reachable from the full app registration path.

**Step 2: Run targeted test**

Run: `uv run pytest tests/routers/test_contracts.py -v`
Expected: FAIL or incomplete coverage.

**Step 3: Write minimal implementation**

Register the new blueprint in `start.py`.

**Step 4: Run tests to verify it passes**

Run: `uv run pytest tests/routers/test_contracts.py -v`
Expected: PASS.

### Task 9: Document how to add contracts, blocks, and fields

**Files:**
- Create: `docs/contracts.md`
- Modify: `README.md`

**Step 1: Write documentation**

Document:
- contract allowlist model
- page blocks model
- supported field types and how to add one
- how to add a new contract handler
- how to add read and write actions
- in-memory flow limitation on process restart

**Step 2: Review docs for consistency**

Check wording against implemented file names and current architecture terminology.

**Step 3: Link the doc from README**

Add a short pointer in the documentation section.

### Task 10: Add swap-pool read-only contract support

**Files:**
- Create: `services/contracts/handlers/swap_pool_contract.py`
- Create: `tests/services/test_swap_pool_contract.py`
- Modify: `services/contracts/registry.py`
- Modify: `routers/contracts.py`
- Modify: `templates/contract_detail.html`
- Modify: `other/stellar_soroban.py`

**Step 1: Write the failing tests**

Add tests for:
- registry entry for the swap contract
- token metadata and 7-decimal amount conversion helpers
- pool overview loading from read-only contract calls
- exact-in and exact-out quote endpoints returning human-readable values

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/services/test_swap_pool_contract.py tests/routers/test_contracts.py -v`
Expected: FAIL because swap handler/routes do not exist yet.

**Step 3: Write minimal implementation**

Implement a dedicated swap handler for the fixed USDM/EURMTL pool, add read-only quote routes, and render pool/quote blocks on the contract page.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_swap_pool_contract.py tests/routers/test_contracts.py -v`
Expected: PASS.

### Task 11: Add swap-pool SEP-7 prepare flows

**Files:**
- Modify: `services/contracts/handlers/swap_pool_contract.py`
- Modify: `routers/contracts.py`
- Modify: `templates/contract_detail.html`
- Modify: `tests/services/test_swap_pool_contract.py`
- Modify: `tests/routers/test_contracts.py`

**Step 1: Add swap prepare coverage**

Add/update tests for:
- swap exact-in SEP-7 prepare helper
- swap exact-out SEP-7 prepare helper
- prepare endpoints returning `request_id`, `uri`, and `qr_url`
- swap contract page rendering address field and SEP-7 buttons

**Step 2: Implement swap write flow**

Implement dedicated prepare helpers for:
- `swap(user, in_idx, out_idx, amount_in, min_amount_out)`
- `swap_strict_receive(user, in_idx, out_idx, amount_out, max_amount_in)`

Reuse the common callback/status flow already used by other contracts.

**Step 3: Verify**

Run targeted lint/tests and `just check-changed`.

### Task 12: Extend swap submission ergonomics

**Files:**
- Modify: `other/stellar_soroban.py`
- Modify: `routers/contracts.py`
- Modify: `templates/contract_detail.html`
- Modify: `tests/routers/test_contracts.py`
- Modify: `tests/services/test_stellar_soroban.py`

**Step 1: Increase prepared transaction validity**

Increase the prepared Soroban transaction timeout from 30 seconds to 5 minutes.
Reflect this on the swap contract page so the user knows the signing window.

**Step 2: Add a direct signed-XDR submit helper**

Add a low-level route for direct manual submit of already signed Soroban XDR:
- validate base64
- submit through Soroban RPC
- log request/result
- return tx hash or decoded network error

**Step 3: Verify**

Run targeted tests plus `just check-changed`.

### Task 13: Add hidden manual signed-XDR send page

**Files:**
- Modify: `routers/contracts.py`
- Create: `templates/contracts_send.html`
- Modify: `tests/routers/test_contracts.py`

**Step 1: Add hidden page**

Add `/contracts/send` as a hidden helper page with:
- textarea for signed XDR
- send button
- result area for tx hash or error

**Step 2: Reuse direct submit logic**

Reuse the low-level signed-XDR submit helper instead of inventing a second Soroban submit path.

**Step 3: Verify**

Run targeted router tests and repo checks.

### Task 14: Improve swap execution robustness

**Files:**
- Modify: `other/stellar_soroban.py`
- Modify: `services/contracts/handlers/swap_pool_contract.py`
- Modify: `routers/contracts.py`
- Modify: `templates/contract_detail.html`
- Modify: `tests/services/test_stellar_soroban.py`
- Modify: `tests/services/test_swap_pool_contract.py`
- Modify: `tests/routers/test_contracts.py`

**Step 1: Fix false-negative submit status handling**

After Soroban `send_transaction`, poll transaction status for a short period instead of assuming immediate finality from a single check.

**Step 2: Add slippage presets to swap prepare flow**

Expose slippage presets in the swap UI and use them when computing:
- `min_amount_out` for exact-in swaps
- `max_amount_in` for exact-out swaps

Current presets:
- `1%`
- `3%`
- `5%`

**Step 3: Verify**

Run targeted tests and repository checks.

### Task 15: Add lazy MMWB generation to prepared contract flows

**Files:**
- Modify: `routers/contracts.py`
- Modify: `templates/contract_detail.html`
- Modify: `tests/routers/test_contracts.py`

**Step 1: Add a flow-bound MMWB route**

Add a route that takes `request_id`, validates the current session marker, reads the stored SEP-7 URI from the prepared flow, and forwards it to `/remote/sep07/add`.

**Step 2: Add lazy frontend action**

Expose a `Generate MMWB button` control in the contracts modal only after prepare succeeds.
Clicking it should fetch the bot link and then reveal an `Open in MMWB` link.

**Step 3: Verify**

Run targeted router tests and repository checks.

### Task 16: Align mountain contract flow with current on-chain capture behavior

**Files:**
- Modify: `services/contracts/handlers/mountain_contract.py`
- Modify: `templates/contract_detail.html`
- Modify: `tests/services/test_mountain_contract.py`
- Modify: `tests/routers/test_contracts.py`

**Step 1: Remove obsolete approve-based preparation**

Prepare the mountain `capture` action as a single contract call without adding external token `approve` wrapping.

**Step 2: Keep amount raw but explain units**

Keep the existing integer/raw input model and add explicit UI help text that raw units are used for EURMTL and that `1 EURMTL = 10,000,000 raw units`.

**Step 3: Verify**

Run targeted router/service tests and changed-file checks.

### Task 17: Run relevant verification gates

**Files:**
- No code changes required

**Step 1: Run focused tests**

Run: `uv run pytest tests/routers/test_contracts.py tests/services/test_contracts_flow_service.py tests/services/test_mountain_contract.py tests/services/test_stellar_soroban.py -v`
Expected: PASS.

**Step 2: Run changed-file quality checks**

Run: `just check-changed`
Expected: PASS for touched Python files.

**Step 3: If `check-changed` is noisy, run at minimum**

Run:
- `just fmt`
- `just lint`
- `just types`

Expected: PASS.
