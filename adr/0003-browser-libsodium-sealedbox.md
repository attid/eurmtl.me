# ADR 0003: Use Browser Libsodium for Stellar Sealed Box

## Status

Accepted

## Context

The Stellar sealed box helper encrypts and decrypts payloads with this algorithm:

1. Decode Stellar StrKey `G...` or `S...` values to Ed25519 key material.
2. Convert Ed25519 keys to Curve25519/X25519 keys.
3. Use libsodium sealed boxes (`crypto_box_seal` / `crypto_box_seal_open`).

The browser page must match the Python helper and must not send private keys,
plaintext, ciphertext, or files to the backend.

## Decision

Vendor `libsodium-sumo` and `libsodium-wrappers-sumo` browser builds under
`static/js/vendor/` and use them from the `/sealedbox` page. Continue using the
existing browser Stellar SDK bundle for StrKey and Stellar keypair handling.

## Consequences

- The browser implementation can be compatible with the Python `PyNaCl`
  sealed box helper.
- The page can keep crypto operations local to the browser tab.
- The page does not depend on a CDN for crypto code.
- Vendored minified JavaScript increases repository size by about 1.3 MB.
- Dependency updates require replacing the vendored files and re-running
  Python-to-JavaScript compatibility checks.
