# SealedBox UX refresh

## Goal

Adapt the browser-only SealedBox page to the UX proposed in `localdoc/sealdbox.html`, while keeping the existing Tabler layout, local static assets, and current Stellar/libsodium algorithm.

## Scope

- Refresh `templates/tabler_sealedbox.html` with a clearer encrypt/decrypt flow.
- Add browser UI wiring in `static/js/sealedbox.js` for mode controls, file dropzones, file chips, seed visibility, result visibility, and key validation hints.
- Update route tests so the expected UX anchors and cache-busted JS asset are covered.

## Constraints

- Do not use the prototype's simulated crypto.
- Do not add external dependencies.
- Keep encryption and decryption compatible with the Python implementation and existing JS helpers.
- Keep the Python CLI and browser JS download links visible.

## Verification

- `uv run --extra dev pytest tests/routers/test_index.py::test_sealedbox_page_exposes_browser_only_crypto_tool -q --no-cov`
- `uv run --extra dev pytest tests/routers/test_index.py -q --no-cov`
- `node --check static/js/sealedbox.js`
- `git diff --check`
- `just check-changed`
