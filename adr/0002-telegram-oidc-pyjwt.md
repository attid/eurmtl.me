# ADR 0002: Use PyJWT for Telegram OIDC ID token validation

## Status

Accepted

## Context

Telegram OpenID Connect login returns an `id_token` that must be validated
server-side. Validation requires JWT signature verification against Telegram
JWKS plus claim checks for issuer, audience, nonce, and expiration.

## Decision

Add `PyJWT[crypto]` as the JWT implementation for Telegram OIDC ID token
validation.

## Consequences

- The application can validate RS256 OIDC tokens using Telegram JWKS.
- The crypto extra provides the cryptographic backend needed for asymmetric JWT
  verification.
- Login tests can mock token retrieval and validation at the helper boundary.
