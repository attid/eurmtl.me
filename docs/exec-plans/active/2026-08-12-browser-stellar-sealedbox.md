# Browser Stellar Sealed Box

## Goal

Add a browser-only Stellar sealed box page that matches `localdoc/stellar_sealedbox.py`
and can be saved or used offline without sending keys or payloads to the backend.

## Scope

- Add public `/sealedbox` page.
- Support text and file encryption to a Stellar `G...` public key.
- Support decrypting base64/raw sealed box data with a Stellar `S...` secret seed.
- Generate a random Stellar keypair in the browser for test/self-use flows.
- Publish the Python CLI helper as a static downloadable file.
- Vendor browser libsodium assets locally so the page is not CDN-dependent.

## Architecture

- Backend only serves static assets and the template. It must not receive private
  keys, plaintext, ciphertext, or selected files.
- Browser code uses existing `static/js/stellar-sdk.min.js` for Stellar StrKey and
  keypair handling.
- Browser code uses vendored `libsodium-sumo` plus `libsodium-wrappers-sumo` for
  `crypto_box_seal`, `crypto_box_seal_open`, and Ed25519-to-Curve25519 conversion.
- The Python CLI remains the compatibility reference; algorithm and IO modes stay
  compatible with the current `localdoc/stellar_sealedbox.py`.

## Files

- Create `adr/0003-browser-libsodium-sealedbox.md`.
- Create `templates/tabler_sealedbox.html`.
- Create `static/js/sealedbox.js`.
- Create `static/docs/stellar_sealedbox.py`.
- Create `static/js/vendor/libsodium-sumo.js`.
- Create `static/js/vendor/libsodium-wrappers-sumo.js`.
- Create `static/js/vendor/libsodium.LICENSE`.
- Modify `routers/index.py`.
- Modify `templates/tabler_base.html`.
- Modify `tests/routers/test_index.py`.

## Tasks

1. Done: Add failing route/template tests for `/sealedbox`, sitemap exposure, local JS
   assets, and Python CLI download link.
2. Done: Add route and template shell until those tests pass.
3. Done: Add vendored libsodium files and ADR documenting why a browser crypto
   dependency is needed.
4. Done: Implement `static/js/sealedbox.js` with pure functions for StrKey conversion,
   keypair generation, seal/open, base64/raw conversion, file IO, and UI wiring.
5. Done: Verify JS-to-Python compatibility by encrypting/decrypting across runtimes.
6. Done: Run focused tests and `just check-changed`.
7. Pending: Commit, push, and run `just push-gitdocker`.

## Verification

- `uv run --extra dev pytest tests/routers/test_index.py -q --no-cov`
- `uv run --extra dev ruff check routers/index.py tests/routers/test_index.py static/docs/stellar_sealedbox.py`
- `uv run --extra dev ruff format --check routers/index.py tests/routers/test_index.py static/docs/stellar_sealedbox.py`
- JS-to-Python and Python-to-JS compatibility smoke test for
  `static/js/sealedbox.js`, libsodium, `static/js/stellar-sdk.min.js`, and
  `static/docs/stellar_sealedbox.py`.
- `just check-changed`
- `just check` currently fails before tests on unrelated baseline formatting:
  `services/xdr_parser.py` would be reformatted and is not changed by this task.
